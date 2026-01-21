# Testing Guide - Authentication API

## Prerequisites

1. Server harus running di http://localhost:8000
2. Anda memiliki access ke Supabase database
3. Email SMTP Hostinger sudah dikonfigurasi di `.env`

## Testing dengan Swagger UI

Buka browser dan kunjungi: http://localhost:8000/docs

## Manual Testing dengan cURL

### 1. Health Check

```bash
curl http://localhost:8000/health
```

Expected Response:
```json
{
  "status": "healthy",
  "app": "Media Monitoring Service",
  "version": "1.0.0"
}
```

### 2. Register User

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "name": "Test User",
    "phone": "081234567890"
  }'
```

Expected Response:
```json
{
  "message": "Registrasi berhasil. Silakan cek email untuk kode OTP.",
  "email": "test@example.com"
}
```

**Note**: Cek email untuk kode OTP yang dikirim.

### 3. Verify Email dengan OTP

```bash
curl -X POST http://localhost:8000/auth/verify-email \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "otp_code": "123456"
  }'
```

Expected Response:
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer"
}
```

**Save the access_token** untuk request selanjutnya.

### 4. Resend OTP (Jika kode kedaluwarsa)

```bash
curl -X POST http://localhost:8000/auth/resend-otp \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com"
  }'
```

### 5. Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "nasriblog12@gmail.com",
    "password": "UtyCantik12"
  }'
```

Expected Response:
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer"
}
```

### 6. Get Current User Info (Protected Route)

```bash
curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Replace `YOUR_ACCESS_TOKEN` dengan token yang didapat dari login.

Expected Response:
```json
{
  "id": 1,
  "email": "test@example.com",
  "name": "Test User",
  "phone": "081234567890",
  "is_active": true,
  "created_at": "2026-01-21T10:30:00Z",
  "workspace_id": null,
  "role_id": null
}
```

### 7. Refresh Token

```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "YOUR_REFRESH_TOKEN"
  }'
```

### 8. Forgot Password (Request OTP)

```bash
curl -X POST http://localhost:8000/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com"
  }'
```

Expected Response:
```json
{
  "message": "Jika email terdaftar, kode OTP akan dikirim",
  "email": "test@example.com"
}
```

### 9. Reset Password dengan OTP

```bash
curl -X POST http://localhost:8000/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "otp_code": "123456",
    "new_password": "newpassword123"
  }'
```

Expected Response:
```json
{
  "message": "Password berhasil direset"
}
```

### 10. Logout

```bash
curl -X POST http://localhost:8000/auth/logout \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Expected Response:
```json
{
  "message": "Logout berhasil"
}
```

## Testing dengan Postman

1. Import collection dari file atau buat manual
2. Buat environment variable:
   - `base_url`: http://localhost:8000
   - `access_token`: (akan diisi otomatis setelah login)
   - `refresh_token`: (akan diisi otomatis setelah login)

3. Test sequence:
   - Register → Verify Email → Login → Get Me → Logout
   - Register → Forgot Password → Reset Password → Login

## Common Issues

### 1. Email tidak terkirim
- Pastikan SMTP credentials benar di `.env`
- Cek firewall atau network blocking port 465
- Cek logs server untuk error messages

### 2. OTP tidak valid atau kedaluwarsa
- OTP berlaku selama 10 menit
- Gunakan endpoint `/auth/resend-otp` untuk mendapatkan OTP baru
- Pastikan OTP yang dimasukkan benar (6 digit)

### 3. Token expired
- Access token berlaku 30 menit
- Gunakan refresh token untuk mendapat access token baru
- Refresh token berlaku 7 hari

### 4. User already exists
- Gunakan email berbeda untuk testing
- Atau hapus user dari database Supabase

## Environment Setup

Pastikan `.env` file sudah dikonfigurasi dengan benar:

```env
# Supabase
SUPABASE_URL=https://xquofgegavueqwgxycoj.supabase.co
SUPABASE_KEY=your_anon_key

# JWT
SECRET_KEY=your_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# SMTP (Hostinger)
SMTP_HOST=smtp.hostinger.com
SMTP_PORT=465
SMTP_USERNAME=info@nusarithm.id
SMTP_PASSWORD=UtyCantik12!!
SMTP_FROM_EMAIL=info@nusarithm.id
SMTP_FROM_NAME=Nusarithm Media Monitoring

# OTP
OTP_EXPIRE_MINUTES=10
OTP_LENGTH=6
```

## Database Check

Cek data di Supabase:

1. **Users Table**: Cek user yang baru dibuat
2. **OTP Codes Table**: Cek OTP yang generated
3. **Roles & Workspace**: Setup jika diperlukan

## API Response Status Codes

| Code | Meaning |
|------|---------|
| 200  | Success |
| 201  | Created (Registration success) |
| 400  | Bad Request (Invalid data) |
| 401  | Unauthorized (Invalid credentials/token) |
| 403  | Forbidden (Account not verified) |
| 404  | Not Found (User not found) |
| 500  | Internal Server Error |

## Next Steps

1. Test semua endpoint satu per satu
2. Verify email notifications diterima
3. Check database entries
4. Test error scenarios
5. Monitor logs untuk debugging

## Support

Jika ada masalah:
1. Cek terminal untuk error logs
2. Cek Supabase logs
3. Verify SMTP settings
4. Contact: info@nusarithm.id
