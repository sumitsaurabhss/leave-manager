# Inter-Service Communication

This document describes how services in the leave management platform communicate with each other, which protocols they use (HTTP vs events), how service discovery works, and what assumptions the design makes about failures, consistency, and security.

---

## Overview

The system uses a hybrid communication model:

- **Synchronous HTTP** via the **API Gateway** for read/write operations invoked directly by clients (e.g., login, apply leave, approve leave).
- **Asynchronous events** via **RabbitMQ** for cross-service side effects and eventual consistency (e.g., initialize leave balances when a user is created, send notifications).

Service locations are not hard-coded; instead, services discover each other dynamically via **Consul**. Distributed tracing via **OpenTelemetry + Jaeger** provides end-to-end visibility across synchronous and asynchronous flows.

---

## Services and Their Roles

- **API Gateway**
  - Sole entry point for clients.
  - Proxies requests to `users-service` and `leave-service`.
  - Applies authentication and passes context downstream.
  - Handles circuit breaking and client-side load balancing using Consul.

- **Users Service**
  - Owns user identities, credentials, roles.
  - Exposes auth and user APIs to the gateway.
  - Publishes domain events (e.g., `employee_created`) to RabbitMQ.

- **Leave Service**
  - Owns leave types, balances, and request lifecycle.
  - Exposes leave-related APIs to the gateway.
  - Consumes `employee.created` and other events.
  - May emit further leave events for notifications.

- **Notification Service**
  - Consumes leave-related events and sends notifications (email/messages).
  - Has no synchronous APIs in the core flow; it is purely event-driven for business logic.

- **Infrastructure**
  - RabbitMQ (message broker).
  - Consul (service registry/discovery).
  - OTel Collector & Jaeger (tracing).

---

## Synchronous HTTP Communication

### Pattern

All client-initiated HTTP traffic goes through the gateway:

```text
Client --> Gateway --> Users Service
Client --> Gateway --> Leave Service
```

The gateway never calls services by fixed hostnames; it uses Consul to resolve service instances and performs client-side load balancing.

### Gateway → Users Service

**Example flows**

- Registration (`POST /auth/register`)
- Login (`POST /auth/token`)
- Get current user (`GET /users/me`)
- List users (`GET /users/` – manager-only)

**Mechanics**

1. Gateway receives HTTP request from client.
2. Gateway validates JWT (where required) and derives `user_id`, `role`, etc.
3. Gateway calls `discover_service_url("users-service")`:
   - Queries Consul: `GET /v1/health/service/users-service?passing`.
   - Randomly selects one healthy instance.
   - Builds base URL, e.g., `http://users-service-<hostname>:8001`.
4. Gateway calls `users-service` via httpx:
   - Adds headers like `Authorization`, `X-Logger-Id` (correlation ID).
   - Wraps call with `users_cb` circuit breaker.
5. Response returned to gateway; gateway forwards body/status to client.

Assumptions:

- Users-service is the **source of truth** for user identity and authentication.
- Gateway never touches user DB directly.
- Circuit breaker thresholds are tuned to fail fast under backend outages and avoid cascading failures.

### Gateway → Leave Service

**Example flows**

- Get leave balance (`GET /leave/balance`)
- Apply leave (`POST /leave/apply`)
- Manager review (`GET /leave/manager/requests`)
- Approve/reject leave (`POST /leave/{id}/approve`, `/reject`)

**Mechanics**

1. Gateway authenticates user and builds headers:
   - `X-User-Id`, `X-User-Email`, `X-User-Role`, `X-Logger-Id`.
2. Resolves `leave-service` via Consul as above.
3. Calls `leave-service` via httpx with `leave_cb` circuit breaker.
4. Leave-service enforces authorization based on `X-User-Role` (e.g., only managers can approve).

Assumptions:

- Authorization decisions are mostly done in leave-service, based on user context passed by gateway.
- Gateway is a trusted component for parsing and validating JWT, but services can still validate claims if needed.

---

## Asynchronous Event Communication

### Pattern

Services publish domain events to RabbitMQ so other services can subscribe without tight coupling:

```text
Users Service  --(employee_created)-->  RabbitMQ  --(employee_created)-->  Leave Service
Leave Service  --(leave_applied/approved/rejected)--> RabbitMQ --> Notification Service
```

This supports eventual consistency between services and isolates side effects (like notification sending).

### Users Service → RabbitMQ → Leave Service

**Event: `employee_created`**

- Trigger: new employee user created in users-service (e.g., role `employee`).
- Publisher: users-service.
- Consumer: leave-service (and potentially others in future).

**Example event payload**

```json
{
  "event_type": "employee_created",
  "data": {
    "user_id": 1,
    "full_name": "Alice Employee",
    "email": "alice.employee@example.com"
  }
}
```

**Flow**

1. After committing the new user, users-service publishes the event to exchange `user.events` with routing key `employee.created`.
2. Leave-service has a queue bound to `user.events` with routing key `employee.created`.
3. Leave-service handler:
   - Creates an internal employee record linked by `external_user_id = user_id`.
   - Initializes leave balances for supported leave types.

Assumptions:

- Event delivery is **at-least-once**:
  - Consumers must be idempotent (e.g., ignore duplicate `employee_created` events for the same `user_id`).
- Event publishing does not participate in a distributed transaction with the DB.

### Leave Service → RabbitMQ → Notification Service

**Events (examples)**

- `leave_applied`
- `leave_approved`
- `leave_rejected`

**Example payload – `leave_applied`**

```json
{
  "event_type": "leave_applied",
  "data": {
    "leave_id": 101,
    "employee_id": 1,
    "employee_email": "alice.employee@example.com",
    "leave_type": "annual",
    "start_date": "2026-06-10",
    "end_date": "2026-06-12",
    "status": "pending"
  }
}
```

**Flow**

1. When a leave request is created/updated, leave-service publishes a corresponding event to a RabbitMQ exchange (e.g., `notifications`).
2. Notification-service subscribes:
   - On `leave.applied`, notifies the manager.
   - On `leave.approved`/`leave.rejected`, notifies the employee.
3. Notification-service may log outcomes in its own DB.

Assumptions:

- Notification failures do **not** affect core leave workflows.
- Notifications may be retried or dead-lettered if delivery fails.

---

## Service Discovery and Load Balancing

### Consul Registration (Producers and Consumers)

Each microservice registers itself with Consul at startup:

- Registration includes:
  - `Name`: logical service name (`users-service`, `leave-service`, `notification-service`).
  - `ID`: unique per instance (e.g., `users-service-<hostname>-8001`).
  - `Address`: container hostname in Docker network.
  - `Port`: internal port (8001 / 8002 / etc.).
  - Optional HTTP health check (`/health`).

Assumptions:

- All services share a Consul agent (in dev, a single `consul` container).
- Health checks reflect readiness to serve traffic (basic liveness for now).

### Gateway Discovery Logic

Gateway uses client-side discovery:

1. Requests `GET /v1/health/service/{service_name}?passing` from Consul.
2. Receives a list of healthy instances with addresses and ports.
3. Chooses one via `random.choice` (simple load balancing).
4. Calls that instance over HTTP.

Assumptions:

- Random selection is sufficient for early-stage load balancing.
- Failures are handled by circuit breakers, not by discovery logic.

---

## Error Handling and Resilience

### Circuit Breakers (Gateway)

For each downstream service, the gateway wraps HTTP calls with a circuit breaker (pybreaker):

- Tracks recent failures (connection errors, 5xx responses) to:
  - Short-circuit further calls when a service is down.
  - Fail fast with `503 Service Unavailable`.
- Automatically transitions from **closed → open → half-open → closed** based on configured thresholds.

Assumptions:

- Breaking at the gateway is preferred over propagating timeouts to clients.
- Breakers are defined per-service (e.g., `users_cb`, `leave_cb`), not per-endpoint.

### Discovery Failures

If Consul has no healthy instances:

- `discover_service_url(service_name)` raises.
- Gateway returns `503` with a descriptive message, e.g.:

```json
{
  "detail": "Leave service discovery error: No healthy instances found for leave-service"
}
```

Assumptions:

- Discovery failure is treated as temporary infrastructure failure.
- Operators can inspect Consul UI and service logs to recover.

### Message Handling on RabbitMQ

Assumptions:

- Events are processed with at-least-once semantics:
  - Consumers confirm messages after successful processing.
  - Failures may cause re-delivery.

---

## Observability and Tracing Across Services

### HTTP Flows

- FastAPI and httpx instrumentation propagate OpenTelemetry trace context across:
  - Client → Gateway → Users Service / Leave Service.
- Jaeger shows a single trace with spans from:
  - Gateway (ingress and outbound calls).
  - Users-service / Leave-service.

### Event Flows

- Manual or library-based instrumentation can add spans when:
  - Publishing events in users-service/leave-service.
  - Consuming events in leave-service/notification-service.
- This allows traces to show causal links between synchronous operations and asynchronous side effects (e.g., user creation → employee_created event → leave balance initialization).

Assumptions:

- For now, HTTP flows are fully instrumented; event flows may be partially instrumented and can be enhanced iteratively.
- Trace IDs may be propagated in event metadata for advanced correlation.

---

## Security and Trust Assumptions

- Gateway is the primary enforcement point for:
  - Authentication (JWT validation).
  - Initial authorization (e.g., manager-only operations).
- Backend services trust headers set by the gateway but:
  - May perform additional authorization checks based on their own data (e.g., leave-service verifying manager status).
- Service-to-service calls are not exposed directly to the internet; only the gateway is externally accessible.

---

## Summary of Key Assumptions

1. **Users-service** is the single source of truth for user identity and roles.
2. **Leave-service** is the single source of truth for leave data and business rules.
3. **Notification-service** is best-effort and does not block core workflow.
4. All services run on a shared network where Consul, RabbitMQ, and OTel Collector are reachable.
5. Event delivery via RabbitMQ is at-least-once; handlers are idempotent.
6. Circuit breakers protect the system from cascading failures.
7. Clients never call backend services directly; they always go through the gateway.