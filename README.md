# Media Monitoring Service - Authentication API

API untuk sistem authentication dengan FastAPI, Supabase, dan Email OTP (SMTP Hostinger).

## Features

- ✅ User Registration dengan email verification
- ✅ Login dengan JWT tokens (access & refresh)
- ✅ Email verification dengan OTP
- ✅ Resend OTP
- ✅ Forgot Password
- ✅ Reset Password dengan OTP
- ✅ Protected endpoints dengan JWT authentication
- ✅ Supabase integration
- ✅ Email service dengan Hostinger SMTP

## Tech Stack

- **FastAPI**: Modern Python web framework
- **Uvicorn**: ASGI server
- **Supabase**: Backend as a Service (Database)
- **JWT**: JSON Web Tokens untuk authentication
- **SMTP**: Email service (Hostinger)
- **Pydantic**: Data validation
- **Bcrypt**: Password hashing

## Project Structure

```
media-monitoring-svc/
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py              # Auth endpoints
│   │   └── dependencies.py      # Auth dependencies
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Configuration settings
│   │   ├── database.py          # Supabase client
│   │   ├── security.py          # Password hashing
│   │   └── jwt.py               # JWT token management
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py              # User models
│   │   ├── token.py             # Token models
│   │   ├── otp.py               # OTP models
│   │   └── password.py          # Password models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py      # Authentication logic
│   │   ├── email_service.py     # Email sending
│   │   └── otp_service.py       # OTP management
│   └── __init__.py
├── main.py                      # FastAPI application
├── requirements.txt             # Python dependencies
├── .env                         # Environment variables
├── .env.example                 # Environment template
└── README.md                    # This file
```

## Installation

### 1. Clone repository

```bash
cd /Volumes/External/Nusarithm/medmon/media-monitoring-svc
```

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup environment variables

Copy `.env.example` to `.env` and update with your credentials:

```bash
cp .env.example .env
```

Edit `.env` file with your Supabase service role key if needed.

## Running the Application

### Development mode

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Or simply:

```bash
python main.py
```

### Production mode

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Authentication

#### 1. Register User
```http
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123",
  "name": "John Doe",
  "phone": "081234567890"
}
```

#### 2. Verify Email
```http
POST /auth/verify-email
Content-Type: application/json

{
  "email": "user@example.com",
  "otp_code": "123456"
}
```

#### 3. Resend OTP
```http
POST /auth/resend-otp
Content-Type: application/json

{
  "email": "user@example.com"
}
```

#### 4. Login
```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

#### 5. Refresh Token
```http
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "your_refresh_token_here"
}
```

#### 6. Forgot Password
```http
POST /auth/forgot-password
Content-Type: application/json

{
  "email": "user@example.com"
}
```

#### 7. Reset Password
```http
POST /auth/reset-password
Content-Type: application/json

{
  "email": "user@example.com",
  "otp_code": "123456",
  "new_password": "newpassword123"
}
```

#### 8. Get Current User
```http
GET /auth/me
Authorization: Bearer {access_token}
```

#### 9. Logout
```http
POST /auth/logout
Authorization: Bearer {access_token}
```

## Database Schema

The API uses the following Supabase tables:

### Users Table
- `id`: bigint (primary key)
- `email`: text
- `password`: text (hashed)
- `name`: text
- `phone`: text
- `is_active`: boolean
- `workspace_id`: bigint (foreign key)
- `role_id`: bigint (foreign key)
- `created_at`: timestamp

### OTP Codes Table
- `id`: bigint (primary key)
- `user_id`: bigint (foreign key)
- `otp_code`: text
- `expires_at`: timestamp
- `is_used`: boolean
- `verified_at`: timestamp
- `created_at`: timestamp

## Security

- Passwords are hashed using bcrypt
- JWT tokens with expiration
- Access tokens expire in 30 minutes
- Refresh tokens expire in 7 days
- OTP codes expire in 10 minutes
- Email verification required before login

## Design Patterns

This project follows clean architecture principles:

1. **Separation of Concerns**: Code organized into layers (API, Services, Models, Core)
2. **Dependency Injection**: Using FastAPI's dependency injection
3. **Repository Pattern**: Supabase client as data access layer
4. **Service Layer**: Business logic separated from API endpoints
5. **DTOs/Schemas**: Pydantic models for data validation
6. **Singleton Pattern**: Supabase client instance

## Error Handling

The API returns consistent error responses:

```json
{
  "detail": "Error message here"
}
```

Common HTTP status codes:
- `200`: Success
- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `500`: Internal Server Error

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| SUPABASE_URL | Supabase project URL | - |
| SUPABASE_KEY | Supabase anon key | - |
| SECRET_KEY | JWT secret key | - |
| SMTP_HOST | SMTP server host | smtp.hostinger.com |
| SMTP_PORT | SMTP server port | 465 |
| SMTP_USERNAME | SMTP username | info@nusarithm.id |
| SMTP_PASSWORD | SMTP password | - |
| OTP_EXPIRE_MINUTES | OTP expiration time | 10 |
| ACCESS_TOKEN_EXPIRE_MINUTES | Access token expiration | 30 |

## Testing

You can test the API using:

1. **Swagger UI**: http://localhost:8000/docs
2. **Postman**: Import the endpoints
3. **cURL**: Command line testing
4. **Python requests**: Write test scripts

Example with cURL:

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123","name":"Test User"}'

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
```

## License

Private - Nusarithm

## Support

For issues and questions, contact: info@nusarithm.id
