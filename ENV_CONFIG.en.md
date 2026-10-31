# Environment configuration guide

This document is the English companion to the Vietnamese `.env` guide in `README.md`.
The English template is `.env.example.en`; the primary template remains `.env.example`.
Neither template contains usable credentials.

## 1. Protect the existing `.env`

- `.env` is local configuration and is ignored by Git. Never commit it or paste its secrets into chat.
- If `.env` already exists, keep it. Compare it with the template and add or change only the values you intend to update.
- Copy a template to `.env` only when no `.env` exists:

  ```powershell
  Copy-Item .env.example .env
  ```

- The Docker Compose environment files are layered. Compose reads them from left to right; later files override earlier values.

## 2. Generate independent secrets

Generate three different random values, one each for `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, and `JWT_SECRET`. Run this command three times and enter each result only in your local environment file:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Each value is 64 hexadecimal characters (32 random bytes). Do not reuse one value for multiple settings. `JWT_SECRET` must be at least 32 characters. Placeholder strings beginning with `REPLACE_WITH_` or `THAY_BANG_` must be replaced before running the services.

## 3. What the main variables do

| Variable | Purpose and guidance |
|---|---|
| `APP_ENV` | Use `local`, `staging`, or `production`. Staging/production do not expose the local `/dev/rooms` test page. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Create the private PostgreSQL service in Compose. The database port is not published to the host. |
| `REDIS_PASSWORD`, `REDIS_PORT` | Protect the Compose Redis service. Its host port is bound to `127.0.0.1` only. |
| `JWT_SECRET` | Signs access tokens. Use an independent random value. |
| `DATABASE_URL`, `REDIS_URL` | Used when FastAPI runs directly on the host. Compose explicitly overrides these inside the container to use its internal PostgreSQL/Redis services. |
| `ACCESS_TOKEN_MINUTES` | Access token lifetime; keep within the application's supported range. |
| `AUTH_COOKIE_SECURE` | Set `false` for local HTTP. Set `true` whenever the browser uses HTTPS, including an HTTPS ngrok URL. |
| `PUBLIC_APP_URL` | Canonical origin used in account and invitation links. Use only scheme, host, and optional port; do not append a path. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact browser origins. Include the scheme and port. Wildcards, paths, query strings, and embedded credentials are invalid. The same allowlist is enforced for WebSockets. |
| `VITE_API_BASE_URL` | Leave empty for same-origin deployment. Nginx proxies `/api/*` and WebSockets to FastAPI. A non-empty value is baked into the frontend at build time and requires rebuilding. |
| `VITE_API_PROXY_TARGET` | Host-run Vite proxy target, normally `http://127.0.0.1:8000`. |
| `BACKEND_BIND_ADDRESS`, `BACKEND_PORT` | Host binding and port for FastAPI. Keep the binding on loopback for local/tunnel testing. |
| `NGINX_BIND_ADDRESS`, `NGINX_HTTP_PORT` | Local Nginx binding and port. Use loopback for local testing; production TLS Compose publishes ports 80/443 explicitly. |
| `SMTP_*` | SMTP host, port, login, password, verified sender, TLS mode, and timeout. Required for email verification, password reset, and room invitations. |
| `RTC_STUN_URLS`, `RTC_TURN_*` | WebRTC ICE servers for voice/video calls. STUN is configured by default; some NATs/firewalls require a TURN server. |
| `NGINX_SERVER_NAME`, `CERTBOT_EMAIL`, `LETSENCRYPT_DIR`, `CERTBOT_WEBROOT_DIR` | Production ACME/TLS configuration. Use a domain you control and keep certificate/webroot directories outside the repository. |

## 4. Configure SMTP

Email-based features return a service-configuration error when the SMTP host, username, password, or sender address is empty.

For Gmail, enable 2-Step Verification and create a Google App Password. Do not use the normal Google account password. A typical STARTTLS setup is:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-address@gmail.com
SMTP_PASSWORD=your-google-app-password
SMTP_FROM_EMAIL=your-address@gmail.com
SMTP_FROM_NAME=Kỳ Tiên Hội
SMTP_USE_SSL=false
SMTP_STARTTLS=true
SMTP_TIMEOUT_SECONDS=10
```

Set `SMTP_USERNAME` to the full account sign-in address. `SMTP_FROM_EMAIL` must be that account or a sender alias authorized by the provider. For implicit TLS, usually port 465, set `SMTP_USE_SSL=true` and `SMTP_STARTTLS=false`; do not enable both modes at once. Other providers may use different hosts, ports, or sender-verification requirements.

Voice/video calls use WebRTC and request camera/microphone access only after a player clicks a call button. Browsers require HTTPS (or localhost). The default STUN server works on many networks, but restrictive NAT/firewalls may require TURN. Configure `RTC_TURN_URLS`, `RTC_TURN_USERNAME`, and `RTC_TURN_CREDENTIAL` with provider-issued credentials; the ICE configuration is sent only to room players, not spectators.

## 5. Run the app locally

### Full Docker Compose stack

The Compose backend uses PostgreSQL and password-protected Redis on its private network. It continues to read SMTP and other application settings from the main `.env`; the host-run SQLite/Redis URLs in `.env` are overridden inside the backend container.

If `.env` is missing any of the three Docker secrets, place the missing values in the ignored `.env.compose.local` file. Do not create or pass this overlay when `.env` already contains all three values. When used, it should contain:

```text
POSTGRES_PASSWORD=<first generated secret>
REDIS_PASSWORD=<second, different generated secret>
JWT_SECRET=<third, different generated secret>
```

Replace all angle-bracketed examples with generated values. Keep the SMTP credentials in `.env`. When secrets are in `.env`, validate and start with:

```powershell
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --build
docker compose --env-file .env ps
```

If secrets are in `.env.compose.local`, append `--env-file .env.compose.local` to each command after `--env-file .env`. Never pass an env-file that does not exist. Keep the same selected file order for `up`, `exec`, `logs`, and `down`.

Open `http://127.0.0.1:8002`. Check `http://127.0.0.1:8002/healthz` and `http://127.0.0.1:8002/api/health`. PostgreSQL and Redis are not exposed publicly. Preserve named volumes with `down`; `down -v` deletes their data.

### FastAPI directly on the host

The host-run default uses SQLite. Configure `REDIS_URL` with the Redis password if using the Compose Redis service, then start Redis and FastAPI:

```powershell
docker compose --env-file .env up -d redis
.\scripts\run-backend.ps1
```

Add `--env-file .env.compose.local` only if the required Redis/Compose secret is stored there.

Run Vite separately with `pnpm dev`; it proxies API and WebSocket traffic to `VITE_API_PROXY_TARGET`.

## 6. Temporary HTTPS/ngrok testing

Do not place an ephemeral ngrok URL in the tracked template or overwrite `.env`. Put tunnel-specific settings in another ignored overlay, for example `.env.ngrok.local`:

```text
APP_ENV=staging
AUTH_COOKIE_SECURE=true
NGINX_BIND_ADDRESS=127.0.0.1
BACKEND_BIND_ADDRESS=127.0.0.1
PUBLIC_APP_URL=https://your-current-ngrok-host
CORS_ALLOWED_ORIGINS=https://your-current-ngrok-host,http://localhost:8002,http://127.0.0.1:8002
```

Use the exact HTTPS origin shown by ngrok, without a trailing path. Tunnel only Nginx:

```powershell
ngrok http 127.0.0.1:8002
docker compose --env-file .env --env-file .env.ngrok.local up -d --no-deps --force-recreate backend nginx
```

If Docker secrets are stored in `.env.compose.local`, pass it after `.env` and before `.env.ngrok.local` in the Compose command.

Never tunnel PostgreSQL, Redis, or the backend port directly. A free ngrok address is temporary; update the overlay whenever the address changes.

## 7. Production

Use `.env.production.example` as the production checklist. Replace every placeholder, configure a real SMTP sender, set `APP_ENV=production` and `AUTH_COOKIE_SECURE=true`, restrict CORS to the actual HTTPS origin, configure DNS and ACME paths outside the repository, then use the production Compose overlays. Do not treat a successful local Compose check or ngrok test as a production deployment or certificate test.
