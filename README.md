# Co Tuong backend

FastAPI backend written in Python. Registration requires email OTP verification
before an account becomes active. Password recovery uses a separate email OTP.

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

## Xiangqi board rules

The pure-Python rules engine is in `app/xiangqi.py`. It models a 9×10 board;
squares are `(row, column)` pairs with row 0 at Black's back rank and column 0
at the a-file. Use `XiangqiState.initial()`, `XiangqiState.from_fen()`, and
`state.to_fen()` to create or serialize a position. FEN uses the six-field WXF
layout (`-` for castling and en-passant fields), uppercase pieces for Red, and
lowercase pieces for Black.

Use `legal_moves()` or `legal_moves_from()` to generate moves,
`apply_move()` to create the next state, and `game_status()` to distinguish
check, checkmate, stalemate, and draw. The engine handles palace/river limits,
horse legs, elephant eyes, cannon screens, check evasion, and generals facing
on an open file. Stalemate is a loss in Xiangqi. Automatic draws currently
cover bare generals, fourfold position repetition, and the 50-move FEN
halfmove clock; tournament adjudication for perpetual checks/chases and other
event-specific rules is not included.

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

## Forgot and reset a password

Request a reset code with `POST /api/v1/auth/forgot-password`:

```json
{
  "email": "player@example.com"
}
```

The API sends a six-digit code to an active account's email. The code is stored
in Redis for 300 seconds. The response is the same whether the email exists or
not.

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

## Public rooms

Create a public room with `POST /api/v1/rooms/`:

```json
{
  "name": "Ván cờ cuối tuần"
}
```

The response returns an auto-incremented room ID, a shareable `join_url`,
the creator's `player1` role, and a secret `participant_token`. Store the token
privately; it authorizes room actions. Set `PUBLIC_APP_URL` to the public web
app origin so generated invitation links point to the deployed app. Until a
login API is added, this token is the room's capability credential.

Use `GET /api/v1/rooms/` to list public rooms waiting for an opponent. Join
from the list or from a shared room link with `POST /api/v1/rooms/{room_id}/join`
and `{}` as the body. The first joiner receives `player2`; later joiners are
spectators. Joining a room that has started is allowed only as a spectator.

The host starts play with `POST /api/v1/rooms/{room_id}/start` and a body
containing the host's `participant_token`. A second player must have joined.
Starting removes the room from the public list, but its share link remains
usable for spectators. `POST /api/v1/rooms/{room_id}/leave` with a participant
token leaves the room; when the host leaves, the room is deleted permanently.

Clients can subscribe to `ws://127.0.0.1:8000/api/v1/rooms/ws` for public lobby
events, and `ws://127.0.0.1:8000/api/v1/rooms/{room_id}/ws?participant_token=...`
for room events. The WebSocket API sends room snapshots and lifecycle events
such as `room.created`, `room.updated`, `room.started`, and `room.closed`.
The WebSocket fan-out is in-process, so run one Uvicorn worker for this version.

## SMTP setup

For Gmail, use `smtp.gmail.com:587` with STARTTLS and an App Password. Google
requires 2-Step Verification to create an App Password. For SendGrid, use
`smtp.sendgrid.net:587`, username `apikey`, and a SendGrid API key as the
password. The sender address must be verified in SendGrid.
