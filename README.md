# Co Tuong backend

FastAPI backend written in Python. Email registration requires OTP verification
before an account becomes active.

## Run locally on Windows

1. Copy `.env.example` to `.env` and set SMTP credentials.
2. Start Redis:

   ```powershell
   docker compose up -d redis
   ```

3. Run the backend in a terminal:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

To run the automated backend tests, install `requirements-dev.txt` and run
`pytest` from the repository root.

The API uses SQLite by default and creates `co_tuong.db` when it starts. Open
<http://127.0.0.1:8000/docs> to try the endpoints.

## Register an account

`POST /api/v1/auth/register`

```json
{
  "email": "player@example.com",
  "password": "secure-password",
  "display_name": "Red General"
}
```

The server creates the account with `is_active=false`, generates a random
six-digit code, stores it in Redis for 300 seconds, and sends it through SMTP.
Passwords are stored as Argon2 hashes. The registration response never contains
the password or its hash.

## Verify the email

`POST /api/v1/auth/verify-email`

```json
{
  "email": "player@example.com",
  "otp": "042781"
}
```

A valid, unexpired code activates the account. Five incorrect attempts expire
the code. Invalid or expired codes return HTTP 400; too many attempts return
HTTP 429.

## SMTP setup

For Gmail, use `smtp.gmail.com:587` with STARTTLS and an App Password. Google
requires 2-Step Verification to create an App Password. For SendGrid, use
`smtp.sendgrid.net:587`, username `apikey`, and a SendGrid API key as the
password. The sender address must be verified in SendGrid.
