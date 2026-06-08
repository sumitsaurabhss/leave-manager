# Leave Manager Microservices

A microservices-based leave management system built with FastAPI, RabbitMQ, Consul, and OpenTelemetry.  
It includes:

- API Gateway
- Users Service
- Leave Service
- Notification Service
- RabbitMQ, Consul, OpenTelemetry Collector, Jaeger

---

## 1. Prerequisites

- Docker (24.x or later) and Docker Compose. [web:377]
- Git
- Optional (local dev without Docker): Python 3.12+, Poetry/pip, PostgreSQL.

Clone the repo:

```bash
git clone <your-repo-url> leave-manager
cd leave-manager
```

---

## 2. Environment Variables

Each service has its own `.env` file under `services/<service>`. These are the key variables you should set or verify.

### 2.1 Gateway (`services/gateway/.env`)

```env
APP_NAME=API Gateway
JWT_SECRET_KEY=super-secret-key
JWT_ALGORITHM=HS256

# Consul config
CONSUL_HOST=consul
CONSUL_PORT=8500

# Optional fallbacks (if Consul is down)
USERS_SERVICE_URL_FALLBACK=http://users-service:8001
LEAVE_SERVICE_URL_FALLBACK=http://leave-service:8002
```

### 2.2 Users Service (`services/users/.env`)

```env
APP_NAME=Users Service

DATABASE_URL=postgresql+asyncpg://user:password@users-db:5432/users

# RabbitMQ
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Consul
CONSUL_HOST=consul
CONSUL_PORT=8500
SERVICE_NAME=users-service
SERVICE_PORT=8001

# OpenTelemetry
OTEL_SERVICE_NAME=users-service
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_TRACES_SAMPLER=parentbased_always_on
```

### 2.3 Leave Service (`services/leave/.env`)

```env
APP_NAME=Leave Service

DATABASE_URL=postgresql+asyncpg://user:password@leave-db:5432/leave

# RabbitMQ
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Consul
CONSUL_HOST=consul
CONSUL_PORT=8500
SERVICE_NAME=leave-service
SERVICE_PORT=8002

# OpenTelemetry
OTEL_SERVICE_NAME=leave-service
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_TRACES_SAMPLER=parentbased_always_on
```

### 2.4 Notification Service (`services/notification/.env`)

```env
APP_NAME=Notification Service

# RabbitMQ
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Consul
CONSUL_HOST=consul
CONSUL_PORT=8500
SERVICE_NAME=notification-service
SERVICE_PORT=8003

# OpenTelemetry
OTEL_SERVICE_NAME=notification-service
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_TRACES_SAMPLER=parentbased_always_on
```

RabbitMQ default credentials (`guest/guest`) come from the Docker image. [web:434]

---

## 3. Running with Docker Compose

### 3.1 Build and Start All Services

From the repo root:

```bash
docker compose up -d --build
```

This starts:

- `gateway` (port `8000`)
- `users-service` (internal 8001)
- `leave-service` (internal 8002)
- `notification-service`
- `rabbitmq` (5672, management UI 15672)
- `consul` (8500)
- `otel-collector` (4317/4318)
- `jaeger` (16686) [web:373][web:377]

### 3.2 Verify Services

- Gateway health:
  ```bash
  curl http://localhost:8000/health
  ```
- Consul UI:
  - http://localhost:8500
- RabbitMQ UI:
  - http://localhost:15672 (user: `guest`, pass: `guest`)
- Jaeger UI:
  - http://localhost:16686/jaeger

You should see the services registered in Consul under `users-service`, `leave-service`, `notification-service`, `gateway`. [web:341][web:347]

### 3.3 Scaling Services (Service Discovery / Load Balancing)

To run multiple instances of backend services and test Consul-based load balancing:

1. Ensure `users-service` and `leave-service` **do not** have `ports:` mapped in `docker-compose.yml` (they should only be on the internal `backend` network).
2. Scale:

   ```bash
   docker compose up -d --scale users-service=3 --scale leave-service=2
   ```

Gateway will use Consul to discover and randomly choose healthy instances per request. [web:412]

---

## 4. Setup: Observability and Tracing

The stack includes OpenTelemetry Collector and Jaeger for distributed tracing. [web:369][web:373][web:377]

- All services export traces to `otel-collector:4317` using OTLP.
- The collector forwards traces to Jaeger.
- You can inspect traces in Jaeger:

  - Open http://localhost:16686/jaeger
  - Select service: `gateway`, `users-service`, `leave-service`, `notification-service`
  - Click “Find Traces” and trigger a few API calls from the client/Postman.

---

## 5. API Testing Instructions

### 5.1 Base URL

All client-facing APIs go through the gateway:

- Base URL: `http://localhost:8000`

### 5.2 Using Postman Collection

A ready-to-use Postman collection JSON is provided at:

- `postman/leave-manager-collection.json`

Steps:

1. Open Postman.
2. Import → select the JSON file.
3. Set collection variables:
   - `base_url`: `http://localhost:8000`
   - `employee_email`: `alice.employee@example.com`
   - `employee_password`: `password123`
   - `manager_email`: `bob.manager@example.com`
   - `manager_password`: `manager`

Recommended flow:

1. **Register users**:
   - `Auth / Register Employee - Success`
   - `Auth / Register Manager - Success`
2. **Login and capture tokens**:
   - `Auth / Login Employee - Success (Get Token)` → saves `employee_token`
   - `Auth / Login Manager - Success (Get Token)` → saves `manager_token`
3. **Test Users APIs**:
   - `Users / GET /users/me - As Employee`
   - `Users / GET /users/ - As Manager`
4. **Test Leave APIs (Employee)**:
   - `Leave - Employee / GET /leave/balance - As Employee`
   - `Leave - Employee / POST /leave/apply - Valid Annual Leave`
   - `Leave - Employee / GET /leave/history - Default (Employee)`
5. **Test Leave APIs (Manager)**:
   - `Leave - Manager / GET /leave/manager/requests - Pending`
   - `Leave - Manager / POST /leave/{id}/approve - Using last_leave_id`
   - `Leave - Manager / POST /leave/{id}/reject - Using last_leave_id`

Error scenarios (401/403/400/422/404) are also included as separate requests in the collection. [web:443][web:441][web:447]

### 5.3 Testing Circuit Breaker / Discovery Failures (Optional)

- Stop a backend service (e.g., `users-service`) and hit `/auth/token` to see gateway return `503` once the circuit breaker opens.
- Deregister instances in Consul or scale down to simulate `No healthy instances found` cases.

---

## 6. Local Development (Optional, Without Docker)

You can run individual services locally for development:

1. Ensure dependencies installed (e.g., via `poetry install` or `pip install -r requirements.txt` per service).
2. Set `.env` values to point to local Postgres/RabbitMQ/Consul or dev containers.
3. Start each FastAPI service with uvicorn, for example:

   ```bash
   cd services/users
   uvicorn app.main:app --reload --port 8001
   ```

   ```bash
   cd services/leave
   uvicorn app.main:app --reload --port 8002
   ```

   ```bash
   cd services/gateway
   uvicorn app.main:app --reload --port 8000
   ```

Note: For local-only runs, adjust `CONSUL_HOST`, `RABBITMQ_HOST`, and OTEL endpoint to match your environment.

---

## 7. Video Recording

A walkthrough video demonstrating:

- Architecture overview.
- Running the stack with Docker Compose.
- Scaling services and observing service discovery in Consul.
- API testing with Postman.
- Viewing distributed traces in Jaeger.

**Video link**:  
https://example.com/leave-manager-demo (replace with your actual recording URL)

---

## 8. Useful URLs Summary

- API Gateway: `http://localhost:8000`
- Gateway health: `http://localhost:8000/health`
- Consul UI: `http://localhost:8500`
- RabbitMQ UI: `http://localhost:15672` (guest / guest)
- Jaeger UI: `http://localhost:16686/jaeger` [web:341][web:347][web:373][web:377]