# API Endpoint Documentation

All endpoints are exposed via the **API Gateway** at `http://localhost:8000`.  
Authentication is JWT-based; most endpoints require a valid `Authorization: Bearer <token>` header.

---

## Auth APIs (Gateway → Users Service)

### POST `/auth/register`

Register a new user (employee or manager). Proxied to `users-service /api/v1/auth/register`.

**Request (JSON)**

```json
POST /auth/register
Content-Type: application/json

{
  "full_name": "Demo Employee",
  "email": "demo.employee@example.com",
  "password": "employee",
  "role": "employee"
}
```

**Successful Response – 201 Created**

```json
{
    "email": "demo.employee@example.com",
    "full_name": "Demo Employee",
    "role": "employee",
    "id": 5
}
```

**Error Responses**

```json
// 400 Bad Request (email already in use)
{
  "detail": "Email already registered"
}
```

```json
// 422 Unprocessable Entity (validation errors)
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

---

### POST `/auth/token`

Login and obtain a JWT access token. Proxied to `users-service /api/v1/auth/token`.

**Request (form-encoded)**

```http
POST /auth/token
Content-Type: application/x-www-form-urlencoded

username=alice.employee@example.com&password=password123
```

**Successful Response – 200 OK**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Response – 401 Unauthorized**

```json
{
  "detail": "Incorrect email or password"
}
```

---

## Users APIs (Gateway → Users Service)

All Users APIs require a valid JWT in the `Authorization` header.

### GET `/users/me`

Get the current authenticated user profile. Proxied to `users-service /api/v1/users/me`.

**Request**

```http
GET /users/me
Authorization: Bearer <access_token>
```

**Successful Response – 200 OK**

```json
{
    "email": "demo.employee@example.com",
    "full_name": "Demo Employee",
    "role": "employee",
    "id": 5
}
```

**Error Response – 401 Unauthorized**

```json
{
  "detail": "Not authenticated"
}
```

---

### GET `/users/`

List all users (manager-only). Proxied to `users-service /api/v1/users/`.

**Request**

```http
GET /users/
Authorization: Bearer <manager_access_token>
```

**Successful Response – 200 OK**

```json
[
  {
    "id": 1,
    "full_name": "Alice Employee",
    "email": "alice.employee@example.com",
    "role": "employee"
  },
  {
    "id": 2,
    "full_name": "Bob Manager",
    "email": "bob.manager@example.com",
    "role": "manager"
  }
]
```

**Error Responses**

```json
// 403 Forbidden (not a manager)
{
  "detail": "Insufficient permissions"
}
```

```json
// 401 Unauthorized
{
  "detail": "Not authenticated"
}
```

---

## Leave APIs (Gateway → Leave Service)

All Leave APIs require a valid JWT. The gateway forwards user identity in headers (`X-User-Id`, `X-User-Email`, `X-User-Role`), and the leave-service enforces authorization.

### GET `/leave/balance`

Get current user’s leave balances across leave types. Proxied to `leave-service /api/v1/leave/balance`.

**Request**

```http
GET /leave/balance
Authorization: Bearer <access_token>
```

**Successful Response – 200 OK**

```json
{
  "employee_id": 1,
  "balances": [
    {
      "leave_type": "annual",
      "allocated": 24,
      "used": 5,
      "remaining": 19
    },
    {
      "leave_type": "sick",
      "allocated": 10,
      "used": 2,
      "remaining": 8
    }
  ]
}
```

**Error – 401 Unauthorized**

```json
{
  "detail": "Not authenticated"
}
```

---

### POST `/leave/apply`

Apply for leave as the current user. Proxied to `leave-service /api/v1/leave/apply`.

**Request (JSON)**

```json
POST /leave/apply
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "leave_type": "annual",
  "start_date": "2026-06-10",
  "end_date": "2026-06-12",
  "reason": "Family vacation"
}
```

**Successful Response – 201 Created**

```json
{
  "id": 101,
  "employee_id": 1,
  "leave_type": "annual",
  "start_date": "2026-06-10",
  "end_date": "2026-06-12",
  "days": 3,
  "status": "pending",
  "reason": "Family vacation",
  "created_at": "2026-06-04T09:30:00.000Z"
}
```

**Error Responses**

```json
// 400 Bad Request (insufficient balance)
{
  "detail": "Insufficient leave balance"
}
```

```json
// 422 Unprocessable Entity (validation)
{
  "detail": [
    {
      "loc": ["body", "start_date"],
      "msg": "start_date must be before end_date",
      "type": "value_error"
    }
  ]
}
```

---

### GET `/leave/history`

Get the current user’s leave history, with optional filters and pagination. Proxied to `leave-service /api/v1/leave/history`.

**Query Parameters**

- `status` (optional): `pending | approved | rejected`.
- `start_date_from` / `start_date_to` (optional): date range.
- `page` (optional, default `1`).
- `page_size` (optional, default `20`).

**Request**

```http
GET /leave/history?status=approved&page=1&page_size=10
Authorization: Bearer <access_token>
```

**Successful Response – 200 OK**

```json
{
  "items": [
    {
      "id": 95,
      "leave_type": "annual",
      "start_date": "2026-05-01",
      "end_date": "2026-05-03",
      "days": 3,
      "status": "approved",
      "reason": "Short trip",
      "approved_by": 2,
      "approved_at": "2026-04-25T10:00:00.000Z"
    }
  ],
  "page": 1,
  "page_size": 10,
  "total_items": 1,
  "total_pages": 1
}
```

---

### GET `/leave/manager/requests`

List leave requests for managers to review. Proxied to `leave-service /api/v1/leave/manager/requests`.

**Authorization**

- Requires the current user to have `role = manager`.

**Query Parameters**

- `status` (optional): filter by status (`pending`, `approved`, `rejected`).
- `employee_id` (optional): filter by employee.
- `start_date_from` / `start_date_to` (optional).
- `page` (default `1`), `page_size` (default `20`).

**Request**

```http
GET /leave/manager/requests?status=pending&page=1&page_size=20
Authorization: Bearer <manager_access_token>
```

**Successful Response – 200 OK**

```json
{
  "items": [
    {
      "id": 101,
      "employee_id": 1,
      "employee_name": "Alice Employee",
      "leave_type": "annual",
      "start_date": "2026-06-10",
      "end_date": "2026-06-12",
      "days": 3,
      "status": "pending",
      "reason": "Family vacation",
      "created_at": "2026-06-04T09:30:00.000Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total_items": 1,
  "total_pages": 1
}
```

**Error Responses**

```json
// 403 Forbidden (not a manager)
{
  "detail": "Insufficient permissions"
}
```

---

### POST `/leave/{leave_id}/approve`

Approve a leave request as a manager. Proxied to `leave-service /api/v1/leave/{leave_id}/approve`.

**Request**

```http
POST /leave/101/approve
Authorization: Bearer <manager_access_token>
```

**Successful Response – 200 OK**

```json
{
  "id": 101,
  "employee_id": 1,
  "leave_type": "annual",
  "start_date": "2026-06-10",
  "end_date": "2026-06-12",
  "days": 3,
  "status": "approved",
  "reason": "Family vacation",
  "approved_by": 2,
  "approved_at": "2026-06-04T09:45:00.000Z"
}
```

**Error Responses**

```json
// 404 Not Found
{
  "detail": "Leave request not found"
}
```

```json
// 409 Conflict (already approved/rejected)
{
  "detail": "Leave request already processed"
}
```

---

### POST `/leave/{leave_id}/reject`

Reject a leave request as a manager with a reason. Proxied to `leave-service /api/v1/leave/{leave_id}/reject`.

**Query Parameter**

- `reason` (required): text reason for rejection.

**Request**

```http
POST /leave/101/reject?reason=Project%20deadlines
Authorization: Bearer <manager_access_token>
```

**Successful Response – 200 OK**

```json
{
  "id": 101,
  "employee_id": 1,
  "leave_type": "annual",
  "start_date": "2026-06-10",
  "end_date": "2026-06-12",
  "days": 3,
  "status": "rejected",
  "reason": "Family vacation",
  "rejected_by": 2,
  "rejected_at": "2026-06-04T09:50:00.000Z",
  "rejection_reason": "Project deadlines"
}
```

**Error Responses**

```json
// 404 Not Found
{
  "detail": "Leave request not found"
}
```

```json
// 409 Conflict (already approved/rejected)
{
  "detail": "Leave request already processed"
}
```

---

## Health Check

### GET `/health`

Health endpoint exposed by the gateway (and similarly by each backend service) for Consul and k8s-style health checks.

**Request**

```http
GET /health
```

**Response – 200 OK**

```json
{
  "status": "ok"
}
```

---

## Error Envelope (Gateway-Level)

When downstream services fail or circuit breakers open, the gateway returns HTTP errors with a simple envelope:

```json
// 503 Service Unavailable (circuit breaker open or discovery failure)
{
  "detail": "Users service temporarily disabled"
}
```

or

```json
{
  "detail": "Leave service discovery error: No healthy instances found for leave-service"
}
```

This provides a consistent client-facing error format even when failures originate in backend microservices or Consul.