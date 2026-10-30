# Kỳ Tiên Hội — Frontend và Backend

Repository này gồm giao diện React/Vite trong `src/` và backend FastAPI trong
`app/`. Frontend gửi lệnh tài khoản, phòng và PvE qua raw WebSocket; lobby và
ván PvP nhận snapshot, nước đi và timer qua các WebSocket chuyên biệt. Các HTTP
route hiện có vẫn được giữ để tương thích với client cũ. `/api/health` và trang
OpenAPI tiếp tục dùng HTTP.

## WebSocket client protocol

Đặt `VITE_API_BASE_URL` trong `.env` (mặc định `http://127.0.0.1:8000`). Các
lệnh tài khoản/phòng/PvE dùng `ws(s)://<backend>/api/v1/ws` theo dạng:

```json
{"id":"request-1","event":"room.create","data":{"room_name":"Bàn cờ","host_name":"Kỳ hữu"}}
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

## Chạy Backend trên Windows

FastAPI backend dùng SQLite mặc định. Redis cần cho luồng phòng/WebSocket; SMTP
cần nếu thử đăng ký OTP hoặc gửi email mời. Hướng dẫn API, ví dụ request và
cách cấu hình chi tiết nằm ở các mục backend bên dưới.

## Backend: run locally on Windows

1. Create the local environment file and set the required values. For example:

   ```powershell
   Copy-Item .env.example .env
   ```

   Set `JWT_SECRET` to a random value of at least 32 characters. Configure SMTP
   credentials before trying registration, password reset, or email invitations.
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

`GET /api/health` checks the database, Redis, and the WebSocket event bridge.
It returns HTTP 200 when all checks are healthy and HTTP 503 with per-service
status otherwise. Application, WebSocket, and Uvicorn logs are JSON lines on
stdout; set `LOG_LEVEL` to change the minimum log level.

For production-style multi-worker runs, keep Redis available and start, for
example, `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`. This
project uses native FastAPI WebSockets, so Redis Pub/Sub relays lobby and room
events between workers while the existing WebSocket protocol stays unchanged.
SQLite is the local development default; production workers should use a
shared database through `DATABASE_URL`.

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
`/demo/rooms` while the API server is running.

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
Each lobby row includes the room ID/code, name, host name, creation timestamp,
player count, and spectator count. Join from the list or from a shared room link
with `POST /api/v1/rooms/{room_id}/join`
and `{}` as the body. For a direct link, send its `token` as `invite_token` in
the join request. If the room has a password, the link token is sufficient;
otherwise send the room `password`. Player 2 marks ready with
`POST /api/v1/rooms/{room_id}/ready` and their `participant_token`. They can
also send `{"type":"ready","ready":true}` on their room WebSocket. The Host's
start request returns `409` until Player 2 is ready. Joining a room that has
started is allowed only as a spectator when spectators are enabled.
The public lobby can also join by numeric room code with
`POST /api/v1/rooms/join` and `{"room_code":"42"}`.
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

The API emails both the numeric room code and `join_url`; SMTP must be configured
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
