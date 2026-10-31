# Kỳ Tiên Hội — Frontend và Backend

Repository này gồm giao diện React/Vite trong `src/` và backend FastAPI trong
`app/`. Frontend gửi lệnh tài khoản, phòng và PvE qua raw WebSocket; lobby và
ván PvP nhận snapshot, nước đi và timer qua các WebSocket chuyên biệt. Các HTTP
route hiện có vẫn được giữ để tương thích với client cũ. `/api/health` và trang
OpenAPI tiếp tục dùng HTTP.

## WebSocket client protocol

Frontend API and WebSocket URLs are same-origin by default. Host-run Vite proxies
`/api/*` to FastAPI using `VITE_API_PROXY_TARGET`; Docker Nginx routes the same
paths to the backend container. Set `VITE_API_BASE_URL` only for an intentionally
separate API origin.

```json
{
  "id": "request-1",
  "event": "room.create",
  "data": { "room_name": "Bàn cờ", "host_name": "Kỳ hữu" }
}
```

Server trả về cùng `id`, `event` kết thúc bằng `.result`, `ok` và `data` hoặc
`error`. Lobby dùng `/api/v1/rooms/ws`; trận PvP dùng
`/api/v1/rooms/{room_id}/ws?participant_token=...`. Nước đi PvP và đồng hồ được
xác thực/phát từ backend. PvE dùng `pve.start`, `pve.player_move` và
`pve.ai_move` trên RPC WebSocket; backend kiểm tra luật trước khi áp dụng nước
đi.

GitHub Actions tự chạy toàn bộ Python tests, compile backend, TypeScript
typecheck và Vite production build cho pull request vào `main` hoặc `developer`.
Để chặn merge khi test lỗi, bật branch protection cho `main` và đặt hai check
`Backend tests` và `Frontend build and typecheck` làm required status checks.

## Chạy frontend trên Windows

Yêu cầu Node.js 22 và pnpm 10.34.3 (được ghim trong `.mise.toml`). Nếu chưa có
pnpm, cài một lần bằng PowerShell:

```powershell
npm install --global pnpm@10.34.3
```

Ảnh/font trong repository được theo dõi bằng Git LFS. Sau khi cài Git LFS, chạy
`git lfs install`; khi clone mà ảnh chưa tải, chạy `git lfs pull`.

Từ thư mục gốc repository:

```powershell
pnpm install --frozen-lockfile
pnpm dev
```

Mở `http://127.0.0.1:8443`. Vite dùng cổng 8443 mặc định và đọc biến môi trường
`PORT` nếu cần đổi cổng. Các lệnh frontend khác:

```powershell
pnpm build
pnpm preview
pnpm format
```

`pnpm preview` chạy bản build; dừng máy chủ dev trước nếu cùng dùng cổng 8443.
Các màn hình và luồng bấm thử được mô tả trong [PROTOTYPE.md](./PROTOTYPE.md).

## Cấu hình file `.env`

`.env.example` là **mẫu hướng dẫn**, không phải bộ thông tin xác thực dùng được ngay.
Nó chứa giá trị giữ chỗ cho các bí mật và để trống SMTP; hãy thay các giá trị cần thiết
trong `.env` ở thư mục gốc. `.env` đã được Git bỏ qua. Nếu file `.env` của bạn đã
có cấu hình, **không chép đè**; so sánh với mẫu rồi chỉ bổ sung các biến còn thiếu.
Chỉ tạo mới bằng `Copy-Item .env.example .env` khi chưa có `.env`. Bản hướng dẫn
tiếng Anh nằm ở [ENV_CONFIG.en.md](./ENV_CONFIG.en.md); mẫu `.env` tiếng Anh là
[.env.example.en](./.env.example.en).

### 1. Tạo ba giá trị bí mật riêng biệt

Chạy lệnh này ba lần, giữ từng kết quả trong máy và điền lần lượt vào
`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET`:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Mỗi kết quả là 64 ký tự hex (32 byte ngẫu nhiên). Không dùng lại cùng một giá
trị, không dùng `REPLACE_WITH_...`, không gửi các giá trị này trong chat và không
commit file `.env`. Có thể dùng `openssl rand -hex 32` thay thế.

### 2. Ý nghĩa các nhóm biến

| Biến | Cách điền |
|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Compose dùng để tạo PostgreSQL nội bộ. Đổi mật khẩu trước khi chạy; không mở cổng DB ra Internet. |
| `REDIS_PASSWORD`, `REDIS_PORT` | Redis trong Compose yêu cầu mật khẩu. `REDIS_PORT` chỉ bind vào `127.0.0.1` để host dev kết nối. |
| `JWT_SECRET` | Bí mật ký access token, tối thiểu 32 ký tự; dùng giá trị ngẫu nhiên riêng. |
| `APP_ENV` | `local` cho máy dev, `staging` cho kiểm thử HTTPS, `production` cho triển khai thật. `staging`/`production` không phục vụ trang test `/dev/rooms`. |
| `DATABASE_URL`, `REDIS_URL` | Dành cho backend chạy trực tiếp trên host. Compose tự ghi đè bằng địa chỉ PostgreSQL/Redis nội bộ của stack. |
| `AUTH_COOKIE_SECURE` | `false` khi chạy HTTP local; bắt buộc `true` khi chạy HTTPS/ngrok. |
| `PUBLIC_APP_URL` | Origin chuẩn dùng trong link email/lời mời, ví dụ `http://localhost:8002`; không thêm path. |
| `CORS_ALLOWED_ORIGINS` | Danh sách origin (nguồn truy cập) cách nhau bằng dấu phẩy, ví dụ `http://localhost:8002,http://localhost:8443`. Phải khớp giao thức, tên máy và port trong trình duyệt; không dùng `*`, đường dẫn hay query. Allowlist này cũng được kiểm tra cho WebSocket. |
| `VITE_API_BASE_URL` | Để trống cho same-origin: Vite/Nginx proxy `/api` và WebSocket. Chỉ điền khi API thực sự nằm ở origin khác; phải build lại frontend sau khi đổi. |
| `VITE_API_PROXY_TARGET` | Backend đích khi chạy Vite trên host, mặc định `http://127.0.0.1:8000`. |
| `BACKEND_BIND_ADDRESS`, `BACKEND_PORT`, `NGINX_BIND_ADDRESS`, `NGINX_HTTP_PORT` | Local nên bind `127.0.0.1`; mặc định API `8000`, giao diện Nginx `8002`. Không bind backend/database/cache trực tiếp ra Internet. |
| `SMTP_*` | Cần cho đăng ký/xác minh email, khôi phục mật khẩu và thư mời. Nếu để trống, các luồng email trả lỗi cấu hình dịch vụ. |
| `RTC_STUN_URLS`, `RTC_TURN_*` | Cấu hình WebRTC cho gọi thoại/video. STUN mặc định có sẵn; một số mạng cần TURN để kết nối được. |

### 3. Cấu hình SMTP

Với Gmail, bật xác minh hai bước rồi tạo **App Password**; không dùng mật khẩu
đăng nhập Gmail. Điền các biến tương ứng trong `.env`:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-address@gmail.com
SMTP_PASSWORD=your-google-app-password
SMTP_FROM_EMAIL=your-address@gmail.com
SMTP_FROM_NAME=Kỳ Tiên Hội
SMTP_USE_SSL=false
SMTP_STARTTLS=true
```

Dùng `SMTP_USERNAME` là địa chỉ đăng nhập đầy đủ; `SMTP_FROM_EMAIL` phải là địa
chỉ đó hoặc alias gửi thư đã được nhà cung cấp cấp quyền. Với SMTP SSL ngầm định
(thường port `465`), đặt `SMTP_USE_SSL=true` và `SMTP_STARTTLS=false`; không bật cả hai.
Không gửi mật khẩu SMTP hoặc mã OTP qua trò chuyện. Sau khi đổi SMTP, khởi động lại backend.

Gọi thoại/video dùng WebRTC và chỉ xin quyền micro/camera sau khi người chơi bấm gọi;
trình duyệt cần HTTPS (hoặc localhost). STUN mặc định hỗ trợ nhiều mạng, nhưng một số
NAT/firewall cần TURN. Điền `RTC_TURN_URLS`, `RTC_TURN_USERNAME` và
`RTC_TURN_CREDENTIAL` từ nhà cung cấp TURN; thông tin này chỉ được gửi trong snapshot
WebSocket của người chơi có token phòng, không gửi cho khán giả.

### 4. Backend chạy trên máy phát triển và Docker Compose

- Backend chạy trực tiếp trên Windows dùng `DATABASE_URL` (mặc định SQLite) và
  `REDIS_URL`. Nếu dùng Redis trong Compose, URL host cần chứa mật khẩu Redis.
- Toàn bộ stack Docker Compose dùng PostgreSQL và Redis riêng trong Docker network;
  nó lấy `SMTP_*`, JWT và các cài đặt khác từ file môi trường nhưng **ghi đè**
  `DATABASE_URL`/`REDIS_URL` bên trong backend container.
- Nếu `.env` thiếu một trong ba bí mật Compose, đặt `POSTGRES_PASSWORD`,
  `REDIS_PASSWORD` và `JWT_SECRET` riêng trong `.env.compose.local` (đã bị Git ignore).
  Nếu `.env` đã có đủ, không cần tạo hoặc nạp overlay. Không truyền một `--env-file`
  không tồn tại vì Compose sẽ dừng với lỗi.

  ```powershell
  # Khi secrets đã có trong .env:
  docker compose --env-file .env config --quiet
  docker compose --env-file .env up -d --build
  docker compose --env-file .env ps

  # Khi secrets nằm trong .env.compose.local, thêm overlay sau .env:
  docker compose --env-file .env --env-file .env.compose.local config --quiet
  docker compose --env-file .env --env-file .env.compose.local up -d --build
  docker compose --env-file .env --env-file .env.compose.local ps
  ```

  Giữ nguyên cùng thứ tự `--env-file` đã chọn cho `exec`, `logs` và `down`. Không dùng
  `down -v` trừ khi chủ động xóa toàn bộ dữ liệu PostgreSQL/Redis.

### 5. Ngrok hoặc HTTPS công khai

Không ghi URL ngrok tạm vào `.env.example`. Dùng file overlay ignored riêng; đặt
`APP_ENV=staging`, `AUTH_COOKIE_SECURE=true`, bind Nginx/backend vào `127.0.0.1`,
và điền origin HTTPS chính xác vào cả `PUBLIC_APP_URL` lẫn
`CORS_ALLOWED_ORIGINS`. Chỉ tunnel Nginx, ví dụ `ngrok http 127.0.0.1:8002`;
không tunnel PostgreSQL, Redis hoặc port backend. Với production, dùng
`.env.production.example`, domain/DNS do bạn quản lý, SMTP thật và quy trình ACME
bên dưới.

## Chạy Backend trên Windows

FastAPI backend dùng SQLite mặc định khi chạy trực tiếp trên host. Redis cần cho
luồng phòng/WebSocket; SMTP chỉ cần cho các luồng email. Sau khi cấu hình `.env`
và cài `requirements.txt`, chạy:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Để chạy backend trực tiếp trên host, hãy khởi động Redis có password bằng đúng
các env file đã chuẩn bị, rồi chạy runner:

```powershell
docker compose --env-file .env up -d redis
.\scripts\run-backend.ps1
```

Nếu Redis/PostgreSQL secrets chỉ có trong `.env.compose.local`, thêm
`--env-file .env.compose.local` sau `.env`.

Backend mở tại `http://127.0.0.1:8000`. Để chạy frontend hot reload đồng thời
với backend/database/cache trong Compose, xem mục “Host-run frontend development”.
Để chạy automated tests, cài `requirements-dev.txt` rồi chạy
`python -m pytest -v` từ thư mục gốc.


## Chạy backend trên Linux / WSL2

Sau khi kích hoạt môi trường ảo và cài các gói trong `requirements.txt`, chạy:

```bash
bash scripts/run-backend.sh
```

Lệnh này chạy `app.main:app` mặc định trên `127.0.0.1:8000` với một worker và uvloop.
Có thể đặt `BACKEND_BIND_ADDRESS` để thay đổi bind address khi thật sự cần.
Script không bật autoreload.

## Origin CORS và WebSocket

`CORS_ALLOWED_ORIGINS` là danh sách origin chính xác, phân cách bằng dấu phẩy.
Khi triển khai, chỉ thêm origin thực tế mà trình duyệt dùng; wildcard bị từ chối.
Backend kiểm tra cùng allowlist này trong mỗi lần bắt tay WebSocket trước khi
chấp nhận kết nối.

## Docker Compose: toàn bộ ứng dụng

Stack mặc định gồm PostgreSQL, Redis có mật khẩu, backend FastAPI và frontend React
được build đa giai đoạn rồi phục vụ qua Nginx. PostgreSQL/Redis chỉ nằm trong mạng
Compose; các port backend và Nginx chỉ bind vào loopback. Backend dùng Python
3.11-slim, uvloop và tài khoản không phải root.

1. Giữ nguyên `.env` hiện có; Compose đọc cấu hình SMTP và ứng dụng từ file đó.
   Trong container, `DATABASE_URL` và `REDIS_URL` được ghi đè để dùng PostgreSQL
   và Redis nội bộ thay vì SQLite/Redis trên host.
2. Nếu `.env` thiếu ba bí mật Compose, thêm `POSTGRES_PASSWORD`, `REDIS_PASSWORD`
   và `JWT_SECRET` vào `.env.compose.local`. Dùng ba giá trị ngẫu nhiên khác nhau;
   không chép SMTP password vào overlay. Nếu secrets đã có trong `.env`, không cần overlay.
3. Kiểm tra cấu hình rồi khởi động bằng `.env`:

   ```bash
   docker compose --env-file .env config --quiet
   docker compose --env-file .env up -d --build
   docker compose --env-file .env ps
   ```

   Nếu secrets nằm trong `.env.compose.local`, thêm
   `--env-file .env.compose.local` ngay sau `--env-file .env` cho mọi lệnh Compose.

4. Mở <http://127.0.0.1:8002>. Kiểm tra `/healthz` của Nginx và `/api/health`
   của PostgreSQL, Redis và cầu nối WebSocket. Xem log bằng
   `docker compose --env-file .env logs -f backend nginx`.
5. Dừng bằng `docker compose --env-file .env down`;
   volume dữ liệu được giữ lại. Chỉ dùng `down -v` khi chủ động xóa toàn bộ dữ liệu.

Khi dùng tunnel HTTPS, giữ Nginx/backend bind vào loopback, đặt
`AUTH_COOKIE_SECURE=true`, và thêm origin HTTPS chính xác vào
`CORS_ALLOWED_ORIGINS` cùng `PUBLIC_APP_URL` trong overlay bị Git bỏ qua. Không
đưa port PostgreSQL hoặc Redis ra Internet.

Dùng `.env.staging.example` để chuẩn bị môi trường staging riêng. Triển khai TLS
trực tiếp cần `.env.production.example`, domain/DNS do bạn quản lý, SMTP thật và
quy trình ACME bên dưới. Chưa có domain/chứng chỉ trong checkout này nên chưa
khẳng định việc cấp mới hoặc gia hạn TLS đã được kiểm thử.

## Phát triển frontend trên máy, backend chạy trong Docker

Để tải lại giao diện tự động khi sửa source, giữ PostgreSQL, Redis và FastAPI trong
Compose rồi chỉ chạy Vite trên máy phát triển. Vite chuyển tiếp `/api/*` và
WebSocket tới backend port 8000:

```powershell
docker compose --env-file .env up -d database redis backend
pnpm dev
```

Nếu secrets nằm trong `.env.compose.local`, thêm
`--env-file .env.compose.local` sau `.env`.

Mở <http://127.0.0.1:8443>. `VITE_API_PROXY_TARGET` mặc định là
`http://127.0.0.1:8000`. Giao diện chạy hoàn toàn trong container ở
<http://127.0.0.1:8002>; Nginx chuyển tiếp cùng các đường dẫn tới FastAPI. Có thể
chạy FastAPI trực tiếp trên host, nhưng cần tự cấu hình `DATABASE_URL` và
`REDIS_URL` trong `.env`; cách đó không cần thiết khi chỉ phát triển frontend.

Nginx dùng HTTP/1.1 Upgrade và timeout proxy 300 giây cho WebSocket. Uvicorn gửi
ping giao thức mỗi 20 giây; trình duyệt tự phản hồi. Endpoint phòng vẫn giữ các
thông điệp JSON `ping`/`pong`.

Bản frontend Docker mặc định dùng API/WebSocket cùng origin. Nginx phục vụ SPA và
chuyển tiếp `/api/*` tới FastAPI; không cần thư mục `dist/` trên host. Khi triển
khai HTTPS, đặt origin thật vào `PUBLIC_APP_URL` và `CORS_ALLOWED_ORIGINS`.

## Thiết lập Nginx HTTPS/WSS (khi đã có domain)

Cấu hình triển khai chính thức nằm trong `compose.acme.yaml`,
`compose.production.yaml`, `compose.certbot.yaml` và
`nginx/production-https.conf.template.example`. Các override cần Compose v2.24.4
trở lên. Đặt dữ liệu Let's Encrypt và ACME webroot bên ngoài repository; `.gitignore`
cũng bỏ qua các thư mục `letsencrypt/` và `certbot/` thường dùng. Trong file
`.env` bị Git bỏ qua, cấu hình `NGINX_SERVER_NAME`, `NGINX_BACKEND_UPSTREAM`,
`CERTBOT_EMAIL`, `LETSENCRYPT_DIR` và `CERTBOT_WEBROOT_DIR` bằng domain bạn sở hữu
và địa chỉ backend thực tế. Trỏ DNS về máy chủ và mở cổng TCP 80/443 trước khi
xin chứng chỉ.

Khởi động máy chủ HTTP tạm để xác thực HTTP-01, xin chứng chỉ, sau đó chuyển sang
cấu hình HTTPS/WSS:

```bash
compose_env=(--env-file .env)
# If Docker secrets are stored in .env.compose.local, uncomment the next line.
# compose_env+=(--env-file .env.compose.local)
docker compose "${compose_env[@]}" -f compose.yaml -f compose.acme.yaml up -d nginx
docker compose "${compose_env[@]}" -f compose.yaml -f compose.acme.yaml -f compose.certbot.yaml \
  --profile certbot run --rm --entrypoint sh certbot -c \
  'certbot certonly --webroot -w /var/www/certbot -d "$CERTBOT_DOMAIN" --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email'
docker compose "${compose_env[@]}" -f compose.yaml -f compose.production.yaml -f compose.certbot.yaml up -d nginx
docker compose "${compose_env[@]}" -f compose.yaml -f compose.production.yaml -f compose.certbot.yaml exec nginx nginx -t
```

Cấu hình production chuyển hướng HTTP sang HTTPS, vẫn phục vụ đường dẫn xác thực
ACME và cung cấp API/WebSocket qua TLS. Lên lịch chạy
`bash scripts/renew-certbot.sh` hằng ngày bằng cron hoặc systemd timer; script gọi
`certbot renew` rồi tải lại Nginx. Chỉ có thể xác nhận yêu cầu chứng chỉ, bắt tay
HTTPS/WSS và quy trình gia hạn sau khi domain thật trỏ tới máy triển khai và được
cấp chứng chỉ tin cậy.

Host-run FastAPI uses SQLite by default and creates `co_tuong.db` when it starts.
Docker Compose uses PostgreSQL and persists it in the `postgres-data` volume. Open
<http://127.0.0.1:8000/docs> for host-run API documentation or
<http://127.0.0.1:8002/docs> when using the Compose stack.

`GET /api/health` checks the database, Redis, and the WebSocket event bridge.
It returns HTTP 200 when all checks are healthy and HTTP 503 with per-service
status otherwise. Application, WebSocket, and Uvicorn logs are JSON lines on
stdout; set `LOG_LEVEL` to change the minimum log level.

The supplied runners use one Uvicorn worker. This project uses native FastAPI
WebSockets, so REST and WebSocket routes share the same ASGI app and port; Redis
Pub/Sub continues to relay lobby and room events. SQLite is the local
development default; production deployments should use a shared database
through `DATABASE_URL`.

## Xiangqi board rules

The pure-Python rules engine is in `app/xiangqi.py`. It models a 9×10 board;
squares are `(row, column)` pairs with row 0 at Black's back rank and column 0
at the a-file. Use `XiangqiState.initial()`, `XiangqiState.from_fen()`, and
`state.to_fen()` to create or serialize a position. FEN uses the six-field WXF
layout (`-` for castling and en-passant fields), uppercase pieces for Red, and
lowercase pieces for Black.

Use `legal_moves()` or `legal_moves_from()` to generate moves,
`make_move()` / `apply_move()` to create the next immutable state, and
`undo_move()` to restore the complete previous state for search. Use
`game_status()` / `game_winner()` to determine the result. The engine handles
palace/river limits, horse legs, elephant eyes, cannon screens, check evasion,
and generals facing on an open file. Stalemate is a loss in Xiangqi.

Tournament history tracks repetition, perpetual checks, basic perpetual
chases, and WXF natural-movecount progress. A perpetual checker loses after a
threefold cycle unless both sides check, which is a draw. An unbroken fourfold
position repetition draws. Natural movecount draws after each side has 100
counted moves without a capture; no more than ten checking moves per side count
toward that limit. Bare generals also draw. The six-field FEN does not contain
the move sequence or natural-movecount metadata, so persist those state fields
alongside FEN when saving an in-progress tournament game. Complex mixed
mating-threat repetitions and perpetual block/offer/exchange adjudication still
require explicit handling.

## Play against the computer

The backend exposes a stateless PvE API at `/api/v1/pve`. Fetch
`GET /api/v1/pve/options` for the starting FEN, side choices (`w` for Red and
`b` for Black), and allowed depths. Start a game with `POST /api/v1/pve/games`:

```json
{
  "player_side": "w",
  "difficulty": "medium",
  "depth": 3
}
```

Difficulty depth ranges are Easy 1–2, Medium 3–4, and Hard 5. Easy sometimes
chooses a random legal move. Medium evaluates material and piece development;
Hard also evaluates central control and check pressure. The server returns the
starting FEN and selected sides. The client keeps the current FEN and requests
the AI turn with `POST /api/v1/pve/ai-move`, sending `fen`, `player_side`,
`difficulty`, and optional `depth`. The response includes the AI move and the
updated FEN. The endpoint returns HTTP 409 when it is the player's turn or the
game has ended.

## Login and remembered sessions

Set `JWT_SECRET` in `.env` to a random value containing at least 32 characters.
The access JWT lasts 15 minutes by default; `ACCESS_TOKEN_MINUTES` can be set
from 15 to 30 minutes.

`POST /api/v1/auth/login` accepts an email or username:

```json
{
  "identifier": "player@example.com",
  "password": "secure-password",
  "remember_me": true
}
```

The response contains `access_token`, `token_type`, and `expires_in`. When
`remember_me` is true, the API stores a hash of a random refresh token in
`user_sessions` and sends the token only in an HttpOnly, Secure,
SameSite=Lax cookie with a 30-day lifetime. `POST /api/v1/auth/refresh` rotates
that cookie and returns a new access token. `POST /api/v1/auth/logout` revokes
the current remembered session and clears the cookie. The Secure cookie is
sent by browsers over HTTPS only.

Registration accepts an optional unique `username`; existing accounts without
one can continue signing in with their email. The startup migration adds the
username column to an existing SQLite demo database without deleting accounts.

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
six-digit code, stores a salted hash in `email_verification_otps` for 300
seconds, and sends the raw code through SMTP. Verification reads and consumes
the code from the database before activating the account.
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

## Forgot and reset a password

Request a reset code with `POST /api/v1/auth/forgot-password`:

```json
{
  "email": "player@example.com"
}
```

The API sends a six-digit code to an active account's email. The code is stored
at `forgot_pwd:{email}` in Redis for 300 seconds. The reset endpoint verifies
the code before changing the password. The response is the same whether the
email exists or not.

Reset the password with `POST /api/v1/auth/reset-password`:

```json
{
  "email": "player@example.com",
  "otp": "042781",
  "new_password": "new-secure-password",
  "confirm_password": "new-secure-password"
}
```

The new password and confirmation must match and be 8–128 characters. A reset
code can be used once; five wrong codes invalidate it.

## Rooms and lobby

Create a room with `POST /api/v1/rooms/`:

```json
{
  "room_name": "Weekend Xiangqi",
  "host_name": "Minh Anh",
  "time_per_move": 30,
  "is_public": true,
  "password": null,
  "allow_spectators": true
}
```

`room_name` is required. `host_name` is optional and defaults to `Khách`.
`time_per_move` accepts 15, 30, or 60 seconds and sets each player's initial
clock. The legacy fields `name` and `timer_seconds` are also accepted.
The local room-creation modal and public lobby demo are available at
`/dev/rooms` (available only when `APP_ENV=local`) while the API server is running.

The response includes an auto-incremented numeric `room_id` (also returned as
the legacy `id`) and a unique `room_uuid`, plus the creator's `player1` role
and secret `participant_token`. Store the
participant token privately; it authorizes room actions. A room password is
hashed before it is stored and is never returned by the API. The response only
includes `has_password`. Public rooms appear in the lobby; private rooms are
omitted. Rooms with `allow_spectators: false` reject joiners after both player
slots are filled and reject spectators after a game starts.

The creator is `player1` (Host/Red). The first successful join receives
`player2` (Black); later joins receive `spectator` when spectators are enabled.
Redis runs seat assignment as one atomic script, so concurrent joins cannot
claim the Player 2 slot twice.

Joining a password-protected room requires `password` in the join body, unless
the client has the room's unguessable invitation token. A private room without
a password can only be joined with its invitation token. For example:

```json
{
  "password": "room-secret"
}
```

Set `PUBLIC_APP_URL` to the web app origin so generated invitation links point
to the deployed app.

The `join_url` has the form `PUBLIC_APP_URL/room/{room_id}?token={invite_token}`.
The invite token is separate from the host's participant token. The frontend can
share or copy this URL with Web Share API / clipboard APIs. Set `PUBLIC_APP_URL`
to a web app that handles `/room/{room_id}` and reads the `token` query value.

Use `GET /api/v1/rooms/` to list only public rooms whose status is `waiting`.
Each lobby row includes the internal room ID and a six-character random
alphanumeric `room_code`, name, host name, creation timestamp,
player count, and spectator count. Join from the list or from a shared room link
with `POST /api/v1/rooms/{room_id}/join`
and `{}` as the body. For a direct link, send its `token` as `invite_token` in
the join request. If the room has a password, the link token is sufficient;
otherwise send the room `password`. Player 2 marks ready with
`POST /api/v1/rooms/{room_id}/ready` and their `participant_token`. They can
also send `{"type":"ready","ready":true}` on their room WebSocket. The Host's
start request returns `409` until Player 2 is ready. Joining a room that has
started is allowed only as a spectator when spectators are enabled.
The public lobby joins with the six-character code using
`POST /api/v1/rooms/join` and `{"room_code":"A7K2Q9"}` (case-insensitive).
Legacy numeric IDs are still accepted temporarily for older invitations.
Clients using the lobby WebSocket can instead send
`{"type":"join_room","room_id":42}`. The socket responds with `room.joined`
and the assigned role plus participant token; use that token to connect to the
room WebSocket.

The host can email an invitation with `POST /api/v1/rooms/{room_id}/invite`:

```json
{
  "email": "friend@example.com",
  "participant_token": "<host participant token>"
}
```

The API emails both the six-character room code and `join_url`; SMTP must be configured
as described below. Only the room host can send email invitations.

The host starts play with `POST /api/v1/rooms/{room_id}/start` and a body
containing the host's `participant_token`. A second player must have joined.
Starting changes status to `playing`, removes the room from the public lobby,
and broadcasts `room.removed` to lobby WebSocket clients. Its share link remains
usable for spectators. `POST /api/v1/rooms/{room_id}/leave` with a participant
token records an intentional leave. If the host leaves while waiting, the room
is deleted and `room.closed` is sent to its players and spectators. If a player
leaves intentionally during a game, the server immediately records a forfeit;
when the host forfeits, `game.forfeit` is broadcast before the room is deleted.
The client should wait for the leave response before closing its WebSocket so
the server can distinguish an intentional exit from a network drop.

An unexpected WebSocket drop is handled separately. During a game, the server
pauses the game clock and grants the disconnected player 60 seconds to reconnect
to the same room WebSocket with the same `participant_token`. The room emits
`player.disconnected` and `player.reconnected`; if the deadline expires, the
server records a forfeit and emits `game.forfeit`. A host disconnect while the
room is waiting still deletes the room and emits `room.closed`.

After start, `GET /api/v1/rooms/{room_id}/game` returns the authoritative FEN,
move version, side to move, both remaining clocks in milliseconds, and server
time, plus `paused`, disconnected players, and their reconnect deadlines. On
the room WebSocket, a player sends a move as
`{"type":"make_move","from":[9,1],"to":[7,0]}`. The server validates it
against `legal_moves()` and broadcasts `move_made` with the updated game state.
It rejects out-of-turn, spectator, stale, and illegal moves. The server charges
the active side's clock and broadcasts `timer_tick` once per second. On expiry,
the server broadcasts `game.timeout` and records the opponent as winner.

Clients can subscribe to `ws://127.0.0.1:8000/api/v1/rooms/ws` for public lobby
events, and `ws://127.0.0.1:8000/api/v1/rooms/{room_id}/ws?participant_token=...`
for room events. The lobby socket sends an initial `rooms.snapshot` containing
waiting rooms, then lifecycle events such as `room.created`, `room.updated`,
and `room.removed`. Redis Pub/Sub relays those events across Uvicorn workers.

## SMTP setup

For Gmail, use `smtp.gmail.com:587` with STARTTLS and an App Password. Google
requires 2-Step Verification to create an App Password. For SendGrid, use
`smtp.sendgrid.net:587`, username `apikey`, and a SendGrid API key as the
password. The sender address must be verified in SendGrid.
