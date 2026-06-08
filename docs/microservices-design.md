# Microservices Design Document

## Overview

This system is a leave management platform built as a set of independently deployable microservices. Each service owns its own data, exposes a REST API, and communicates via:

- Synchronous HTTP calls (through an API Gateway).
- Asynchronous events via RabbitMQ.

Service discovery is handled by Consul, and distributed tracing is implemented with OpenTelemetry and Jaeger. [web:428][web:432][web:437]

---

## Services and Responsibilities

### API Gateway

**Responsibilities**

- Single external entrypoint for clients (web, mobile).
- Routes and proxies requests to backend services.
- Performs authentication (JWT verification) and attaches user context headers (user id, role, email) for downstream services.
- Implements circuit breakers for:
  - `users-service` (auth and user-related APIs).
  - `leave-service` (leave-related APIs).
- Uses Consul for service discovery and client-side load balancing across multiple instances of backend services. [web:428][web:412]

**Key Technologies**

- FastAPI
- pybreaker (circuit breaker)
- Consul (service discovery)
- httpx (HTTP client, instrumented with OpenTelemetry)

---

### Users Service

**Responsibilities**

- Manages user accounts, authentication, and roles (employee, manager).
- Exposes APIs for:
  - User registration.
  - Login/token issuance.
  - Current user profile (`/users/me`).
  - Listing users (manager-only). [web:431][web:435]
- Owns user credentials and profile data.
- Emits events such as `employee_created` to RabbitMQ when new employees are created, allowing other services to react. [web:431][web:434]

**Key Technologies**

- FastAPI
- SQLAlchemy + relational database
- RabbitMQ (producer)
- Consul registration
- OpenTelemetry (FastAPI instrumentation)

---

### Leave Service

**Responsibilities**

- Manages:
  - Leave types.
  - Employee leave balances.
  - Leave requests lifecycle: apply, approve, reject.
- Exposes APIs for:
  - Viewing leave balance.
  - Applying for leave.
  - Manager approval/rejection flows.
  - Viewing leave history. [web:431][web:435]
- Subscribes to `employee_created` events from the users-service (via RabbitMQ) to:
  - Create internal employee records.
  - Initialize leave balances. [web:431][web:434]

**Key Technologies**

- FastAPI
- SQLAlchemy + relational database
- RabbitMQ (consumer and event publisher for leave events)
- Consul registration
- OpenTelemetry (FastAPI instrumentation)

---

### Notification Service

**Responsibilities**

- Handles async notifications (e.g., email or other channels) for:
  - Leave applied.
  - Leave approved.
  - Leave rejected.
- Subscribes to relevant events from RabbitMQ (e.g., `leave.applied`, `leave.approved`). [web:431][web:435]

**Key Technologies**

- FastAPI (for health/status APIs) or background worker
- RabbitMQ (consumer)
- Consul registration
- OpenTelemetry (FastAPI or manual instrumentation)

---

### Infrastructure Services

#### RabbitMQ

- Message broker for event-driven communication between services.
- Uses exchanges such as `hr.events` and appropriate routing keys (`employee.created`, `leave.applied`, etc.).
- Enables loose coupling between services (users → leave, users/leave → notification). [web:434]

#### Consul

- Central service registry for all microservices.
- Each service registers itself with:
  - `Name` (logical service name, e.g. `users-service`).
  - `ID` (unique per container/instance).
  - `Address` (container hostname).
  - `Port` (service port inside Docker network).
  - HTTP health check (e.g. `/health`). [web:341]
- Gateway queries Consul to discover healthy instances of backend services. [web:347]

#### OpenTelemetry Collector & Jaeger

- OpenTelemetry Collector:
  - Receives traces from all services via OTLP (gRPC/HTTP).
  - Processes and batches spans.
  - Exports traces to Jaeger. [web:373][web:377]
- Jaeger:
  - Distributed tracing UI for visualizing request flows across gateway and services.
  - Useful for performance analysis and debugging cross-service issues. [web:369]

---

## Architecture Diagram

High-level architecture (logical view):

```text
          +-------------------+
          |      Clients      |
          |  (Web / Mobile)   |
          +---------+---------+
                    |
                    v
          +-------------------+
          |    API Gateway    |
          | - Auth & JWT      |
          | - Circuit Breaker |
          | - Consul SD       |
          +----+---------+----+
               |         |
     HTTP      |         | HTTP
 (users API)   |         | (leave API)
               |         |
               v         v
    +----------------+  +----------------+
    |  Users Service |  |  Leave Service |
    | - Users/Auth   |  | - Leave Rules  |
    | - Roles        |  | - Balances     |
    +-------+--------+  +--------+-------+
            |                    |
            | RabbitMQ events    | RabbitMQ events
            v                    v
      +------------------------------------+
      |           RabbitMQ (Broker)        |
      |  Exchanges: hr.events, ...         |
      +----------------+-------------------+
                       |
                       v
              +---------------------+
              | Notification Service|
              | - Async notifications
              +---------------------+


  +-------------+       +------------------+
  |   Consul    |<----->| All Services     |
  |  Registry   |       | - Register       |
  |             |       | - Health Checks  |
  +-------------+       +------------------+

  +-------------------+      +---------------------------+
  | OTel Collector    |<-----| All Services (OTLP)      |
  +---------+---------+      +--------------+-----------+
            |                               |
            v                               v
        +-----------------------------+
        |          Jaeger            |
        | Distributed Tracing UI     |
        +---------------------------+
```

This diagram shows:

- API Gateway mediating client traffic.
- Users / Leave / Notification services behind the gateway.
- RabbitMQ for asynchronous event flow.
- Consul for service registry/discovery.
- OpenTelemetry Collector & Jaeger for tracing. [web:428][web:369][web:373]

---

## Communication Patterns

### Synchronous: HTTP via API Gateway

**Clients → Gateway**

- RESTful HTTP endpoints, with JWT tokens for authentication.
- The gateway validates tokens and attaches user context via headers (`X-User-Id`, `X-User-Email`, `X-User-Role`, `X-Logger-Id`).

**Gateway → Users Service**

- Example routes:
  - `POST /auth/register` → `users-service /api/v1/auth/register`
  - `POST /auth/token` → `users-service /api/v1/auth/token`
  - `GET /users/me` → `users-service /api/v1/users/me`
- Flow:
  - Gateway resolves `users-service` via Consul.
  - Picks a random healthy instance (client-side load balancing).
  - Wraps the outbound HTTP call in a circuit breaker (pybreaker). [web:341][web:347][web:412]

**Gateway → Leave Service**

- Example routes:
  - `GET /leave/balance` → `leave-service /api/v1/leave/balance`
  - `POST /leave/apply` → `leave-service /api/v1/leave/apply`
  - `GET /leave/manager/requests` → `leave-service /api/v1/leave/manager/requests`
  - `POST /leave/{id}/approve`, `POST /leave/{id}/reject`
- Same flow: Consul discovery + client-side load balancing + circuit breaker. [web:412]

---

### Asynchronous: Events via RabbitMQ

**Users Service → RabbitMQ**

- On user/employee creation:
  - Publishes `employee_created` event to an exchange (e.g. `hr.events`) with routing key like `employee.created`.

**Leave Service**

- Subscribes to `employee.created` events:
  - Creates internal employee reference.
  - Initializes leave balances for the new employee. [web:431][web:435]

**Notification Service**

- Subscribes to leave lifecycle events from RabbitMQ:
  - `leave.applied`, `leave.approved`, `leave.rejected`.
- Sends notifications to employees/managers as needed. [web:431][web:434]

Asynchronous communication decouples services: if notification-service is down, users and leave services can still operate and publish events, which will be processed when notification-service is back. [web:434]

---

## Service Discovery and Load Balancing

### Consul Registration (per Service)

Each service uses a helper like `register_service` to register itself with Consul:

- `Name`: logical service name (e.g., `"users-service"`).
- `ID`: unique instance ID (e.g., `"users-service-<hostname>-8001"`).
- `Address`: container hostname (inside Docker network).
- `Port`: service’s internal port (e.g., 8001).
- Optional HTTP health check (e.g., `GET http://<address>:<port>/health`). [web:341]

Multiple instances of the same service (scaled via Docker Compose) register under the same `Name` but with different `ID` and `Address`.

### Gateway Discovery Logic

The gateway’s `discover_service_url(service_name)`:

1. Calls Consul:

   - `GET /v1/health/service/{service_name}?passing` to list healthy instances. [web:347]

2. If no healthy instances exist, it raises a runtime error (translated to HTTP 503).

3. Otherwise:
   - Selects a random instance from the list (`random.choice`).
   - Builds a base URL: `http://{address}:{port}`.
   - Uses this base URL for the outbound HTTP call.

This implements simple client-side load balancing across all healthy instances of a service. [web:412]

---

## Observability and Tracing

### OpenTelemetry Setup

Each service initializes OpenTelemetry tracing:

- Sets a `TracerProvider` with a `Resource` containing `service.name` (e.g., `"gateway"`, `"users-service"`, `"leave-service"`, `"notification-service"`). [web:369][web:374]
- Configures an OTLP exporter pointing at:
  - `OTEL_EXPORTER_OTLP_ENDPOINT = http://otel-collector:4317`.
- Adds a `BatchSpanProcessor` to send spans efficiently. [web:373][web:377]

### Instrumentation

- Gateway:
  - `FastAPIInstrumentor.instrument_app(app)` for incoming HTTP requests.
  - `HTTPXClientInstrumentor().instrument()` for outgoing HTTP calls to backend services. [web:374]
- Backend services:
  - `FastAPIInstrumentor.instrument_app(app)` to trace incoming HTTP requests.
- Context propagation:
  - OpenTelemetry injects/extracts trace context headers automatically for httpx calls, so a request from client → gateway → users-service → leave-service appears as a single trace in Jaeger. [web:369][web:371]

### Jaeger

- The OTel Collector exports traces to Jaeger.
- You can view:
  - End-to-end request timelines.
  - Service dependency graphs.
  - Slow spans and error traces. [web:369][web:373]

---

## Data Management

- Each microservice has its own database:
  - **Users Service DB**:
    - Users, credentials (hashed passwords), roles, profile data.
  - **Leave Service DB**:
    - Employees, leave types, leave balances, leave requests (status, dates, approver, etc.).
  - **Notification Service DB (optional)**:
    - Notification templates, outbox, delivery logs.

- There is no shared database; cross-service data flows through HTTP APIs or events. This aligns with microservice best practices for isolation and independent scaling. [web:428][web:432][web:437]

---

## Fault Tolerance and Resilience

### Circuit Breakers

- Implemented via pybreaker at the gateway on:
  - Calls to `users-service`.
  - Calls to `leave-service`.
- Configuration:
  - `fail_max`: number of failures before opening the breaker.
  - `reset_timeout`: wait time before transitioning to half-open. [web:429]
- Behavior:
  - When downstream services are failing or unavailable, the gateway quickly responds with HTTP 503 instead of blocking or cascading failures. [web:412]

### Health Checks and Service Removal

- Consul health checks:
  - Periodically call each service’s `/health` endpoint.
  - Mark instances as unhealthy if checks fail.
  - Unhealthy instances are excluded from discovery results (`?passing` filter). [web:341][web:347]

### Asynchronous Decoupling

- RabbitMQ decouples core workflows from side effects:
  - Core operations (e.g., creating a user, applying for leave) are not blocked by notification or downstream side effects.
  - Consumers can catch up when back online. [web:434]

---

## Deployment and Scaling

### Docker Compose (Local/Dev)

- Services:
  - `gateway`, `users-service`, `leave-service`, `notification-service`.
- Infrastructure:
  - `rabbitmq`, `consul`, `otel-collector`, `jaeger`.
- Shared `backend` network.

Scaling is achieved with:

```bash
docker compose up -d --scale users-service=3 --scale leave-service=2
```

- Each instance self-registers in Consul.
- Gateway uses client-side load balancing across all healthy instances. [web:412][web:341]

### Future: Kubernetes or Other Orchestrators

The same architecture can be migrated to:

- Kubernetes Deployments + Services (for service discovery and load balancing).
- A managed service mesh (e.g., Consul Connect, Istio) if required.
- Externalized configuration and secrets management.

Core design (services, communication patterns, observability) remains the same. [web:411][web:416]

---

## Appendix: Future Extensions

Potential future enhancements:

- **API versioning** at the gateway for backward compatibility.
- **Rate limiting** and **API keys** at the gateway.
- **Saga patterns** and outbox patterns for more complex, cross-service transactions.
- **RBAC** and fine-grained authorization for manager vs employee workflows.

These can be added without changing the fundamental microservices design described here. [web:428][web:431]