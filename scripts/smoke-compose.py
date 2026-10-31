"""Smoke-test the running Docker Compose stack without printing credentials."""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import subprocess
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import websockets


def run_compose(env_files: list[Path], *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose"]
    for env_file in env_files:
        command.extend(("--env-file", str(env_file)))
    command.extend(args)
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
    )


def seed_accounts(env_files: list[Path]) -> dict[str, Any]:
    script = r'''
import json, secrets
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User
from app.security import hash_password
prefix = secrets.token_hex(6)
accounts = []
with SessionLocal() as session:
    for color, display_name in (("red", "Live Smoke Red"), ("black", "Live Smoke Black")):
        password = secrets.token_urlsafe(24)
        user = User(
            email=f"{prefix}-{color}@example.invalid",
            username=f"smoke{prefix}{color}",
            display_name=f"{display_name} {prefix[:4]}",
            password_hash=hash_password(password),
            is_active=True,
        )
        session.add(user)
        session.flush()
        accounts.append({"id": user.id, "email": user.email, "name": user.display_name, "password": password})
    session.commit()
print(json.dumps({"prefix": prefix, "accounts": accounts}))
'''
    result = run_compose(env_files, "exec", "-T", "backend", "python", "-c", script)
    return json.loads(result.stdout.strip().splitlines()[-1])


def remove_smoke_data(env_files: list[Path], prefix: str, room_id: int | None) -> None:
    script = r'''
import os
from sqlalchemy import delete, func, or_, select
from app.database import SessionLocal
from app.models import Match, User, UserSession
from app.room_store import delete_room, get_room, get_room_id_by_code
prefix = os.environ["SMOKE_PREFIX"]
room_id = int(os.environ["SMOKE_ROOM_ID"])
with SessionLocal() as session:
    users = list(session.scalars(select(User).where(User.username.like(f"smoke{prefix}%"))).all())
    ids = [user.id for user in users]
    if ids:
        session.execute(delete(Match).where(or_(Match.red_user_id.in_(ids), Match.black_user_id.in_(ids))))
        session.execute(delete(UserSession).where(UserSession.user_id.in_(ids)))
        for user in users:
            session.delete(user)
        session.commit()
    remaining_users = session.scalar(select(func.count()).select_from(User).where(User.username.like(f"smoke{prefix}%"))) or 0
    if remaining_users:
        raise RuntimeError("Smoke-test accounts were not fully removed")
    remaining_sessions = 0
    remaining_matches = 0
    if ids:
        remaining_sessions = session.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id.in_(ids))) or 0
        remaining_matches = session.scalar(
            select(func.count()).select_from(Match).where(or_(Match.red_user_id.in_(ids), Match.black_user_id.in_(ids)))
        ) or 0
    if remaining_sessions or remaining_matches:
        raise RuntimeError("Smoke-test sessions or match records were not fully removed")
if room_id > 0:
    room = get_room(room_id)
    room_code = room["room_code"] if room is not None else None
    delete_room(room_id)
    if get_room(room_id) is not None:
        raise RuntimeError("Smoke-test room was not removed")
    if room_code and get_room_id_by_code(room_code) is not None:
        raise RuntimeError("Smoke-test room code index was not removed")
print("smoke data removed and verified")
'''
    run_compose(
        env_files,
        "exec",
        "-T",
        "-e",
        f"SMOKE_PREFIX={prefix}",
        "-e",
        f"SMOKE_ROOM_ID={room_id or 0}",
        "backend",
        "python",
        "-c",
        script,
    )


def api_request(base_url: str, path: str, *, body: dict[str, Any] | None = None, token: str | None = None) -> Any:
    headers = {"Accept": "application/json"}
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{base_url}{path}", data=payload, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


async def rpc(websocket: Any, event: str, data: dict[str, Any]) -> dict[str, Any]:
    request_id = str(uuid.uuid4())
    await websocket.send(json.dumps({"id": request_id, "event": event, "data": data}))
    while True:
        response = json.loads(await asyncio.wait_for(websocket.recv(), timeout=12))
        if response.get("id") != request_id:
            continue
        if not response.get("ok"):
            raise RuntimeError(f"WebSocket RPC {event} failed: {response.get('error', {}).get('status')}")
        return response["data"]


async def receive_type(websocket: Any, *types: str) -> dict[str, Any]:
    while True:
        event = json.loads(await asyncio.wait_for(websocket.recv(), timeout=12))
        if event.get("type") == "error":
            raise RuntimeError(f"Room WebSocket failed: {event.get('reason')}")
        if event.get("type") in types:
            return event


async def exercise(base_url: str, accounts: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    origin: Any = base_url
    api_prefix = "/api/v1"
    tokens = []
    for account in accounts:
        session = api_request(
            base_url,
            f"{api_prefix}/auth/login",
            body={"identifier": account["email"], "password": account["password"], "remember_me": False},
        )
        tokens.append(session["access_token"])

    app_shell = urllib.request.urlopen(base_url, timeout=10).read().decode("utf-8", "replace")
    if "<div id=\"root\">" not in app_shell:
        raise AssertionError("Frontend SPA shell was not served")
    health = api_request(base_url, "/api/health")
    if health["status"] != "ok":
        raise AssertionError(f"Backend health is not ok: {health['status']}")
    community = api_request(base_url, f"{api_prefix}/community/summary")
    if community["registered_players"] < 2:
        raise AssertionError("PostgreSQL-backed community count did not include the test accounts")

    rpc_url = base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    async with websockets.connect(f"{rpc_url}{api_prefix}/ws", origin=origin) as command_socket:
        options = await rpc(command_socket, "pve.options", {})
        if "easy" not in options["difficulties"]:
            raise AssertionError("PvE options were not returned by the live backend")
        pve_game = await rpc(command_socket, "pve.start", {"player_side": "w", "difficulty": "easy"})
        user_move = await rpc(
            command_socket,
            "pve.player_move",
            {"fen": pve_game["fen"], "player_side": "w", "from": [9, 1], "to": [7, 0]},
        )
        ai_move = await rpc(
            command_socket,
            "pve.ai_move",
            {"fen": user_move["fen"], "player_side": "w", "difficulty": "easy"},
        )
        if ai_move["fen"] == pve_game["fen"]:
            raise AssertionError("Live PvE engine did not return a move")
        room = await rpc(
            command_socket,
            "room.create",
            {"room_name": "Compose smoke game", "host_name": "untrusted host", "auth_token": tokens[0]},
        )
        room_id = int(room["id"])
        if room["host_name"] != accounts[0]["name"]:
            raise AssertionError("The server did not bind the authenticated host identity")
        joined = await rpc(
            command_socket,
            "room.join",
            {"room_id": room_id, "participant_name": "untrusted player", "auth_token": tokens[1]},
        )
        if joined["player2_name"] != accounts[1]["name"]:
            raise AssertionError("The server did not bind the authenticated opponent identity")
        await rpc(command_socket, "room.ready", {"room_id": room_id, "participant_token": joined["participant_token"]})
        await rpc(command_socket, "room.start", {"room_id": room_id, "participant_token": room["participant_token"]})

    host_url = f"{rpc_url}{api_prefix}/rooms/{room_id}/ws?participant_token={room['participant_token']}"
    black_url = f"{rpc_url}{api_prefix}/rooms/{room_id}/ws?participant_token={joined['participant_token']}"
    async with websockets.connect(host_url, origin=origin) as red_ws, websockets.connect(black_url, origin=origin) as black_ws:
        red_snapshot = json.loads(await asyncio.wait_for(red_ws.recv(), timeout=12))
        black_snapshot = json.loads(await asyncio.wait_for(black_ws.recv(), timeout=12))
        if red_snapshot.get("type") != "room.snapshot" or black_snapshot.get("type") != "room.snapshot":
            raise AssertionError("Room participants did not receive authoritative snapshots")
        await red_ws.send(json.dumps({"type": "call_signal", "action": "request", "mode": "audio"}))
        call_request = await receive_type(black_ws, "call_signal")
        if call_request.get("action") != "request" or call_request.get("mode") != "audio":
            raise AssertionError("Player-to-player call signaling was not relayed")
        await red_ws.send(json.dumps({"type": "call_signal", "action": "cancel"}))
        call_cancel = await receive_type(black_ws, "call_signal")
        if call_cancel.get("action") != "cancel":
            raise AssertionError("Call cancellation was not relayed")
        await red_ws.send(json.dumps({"type": "make_move", "from": [9, 1], "to": [7, 0]}))
        red_move, black_move = await asyncio.gather(receive_type(red_ws, "move_made"), receive_type(black_ws, "move_made"))
        if red_move["game"]["version"] != 1 or black_move["game"]["version"] != 1:
            raise AssertionError("The first move was not synchronized to both participants")
        await black_ws.send(json.dumps({"type": "make_move", "from": [0, 1], "to": [2, 0]}))
        await asyncio.gather(receive_type(red_ws, "move_made"), receive_type(black_ws, "move_made"))
        await red_ws.send(json.dumps({"type": "resign"}))
        await asyncio.gather(receive_type(red_ws, "game_over"), receive_type(black_ws, "game_over"))

    red_matches, black_matches, red_stats, black_stats = [
        api_request(base_url, f"{api_prefix}/users/me/matches", token=tokens[0]),
        api_request(base_url, f"{api_prefix}/users/me/matches", token=tokens[1]),
        api_request(base_url, f"{api_prefix}/users/me/stats", token=tokens[0]),
        api_request(base_url, f"{api_prefix}/users/me/stats", token=tokens[1]),
    ]
    if len(red_matches) != 1 or len(black_matches) != 1:
        raise AssertionError("The completed online match was not persisted for both players")
    match = red_matches[0]
    if match["match_key"] != black_matches[0]["match_key"] or len(match["notation"].split()) != 4:
        raise AssertionError("The persisted match record or coordinate notation is incomplete")
    if red_stats["elo"] != 984 or black_stats["elo"] != 1016:
        raise AssertionError("PostgreSQL Elo updates were not applied as expected")
    return room_id, {
        "frontend": "ok",
        "api_health": health["status"],
        "database": health["checks"]["database"]["status"],
        "redis": health["checks"]["redis"]["status"],
        "websocket_event_bus": health["checks"]["websocket"]["status"],
        "pve_ai": "ok",
        "room_websocket": "ok",
        "persisted_match": "ok",
        "replay_notation_tokens": len(match["notation"].split()),
        "red_elo_change": match["red_elo_change"],
        "black_elo_change": match["black_elo_change"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, action="append")
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    args = parser.parse_args()
    env_files = args.env_file or [Path(".env.local.example")]
    accounts = seed_accounts(env_files)
    room_id = None
    try:
        room_id, result = asyncio.run(exercise(args.base_url.rstrip("/"), accounts["accounts"]))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    finally:
        remove_smoke_data(env_files, accounts["prefix"], room_id)


if __name__ == "__main__":
    main()
