"""Create, join, start, leave, and observe public game rooms."""

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from ..email_service import (
    EmailConfigurationError,
    EmailDeliveryError,
    send_room_invitation_email,
)
from ..room_hub import room_hub
from ..room_schemas import (
    RoomAccessResponse,
    RoomActionRequest,
    RoomCodeJoinRequest,
    RoomCreateRequest,
    RoomInviteRequest,
    RoomInviteResponse,
    RoomGameSnapshot,
    RoomJoinRequest,
    RoomLeaveResponse,
    RoomMoveRequest,
    RoomSummary,
)
from ..room_store import (
    create_room,
    apply_game_move,
    get_participant_role,
    get_room,
    get_game_snapshot,
    get_or_create_invite_token,
    is_valid_invite_token,
    join_room,
    leave_room,
    list_public_rooms,
    mark_player_disconnected,
    mark_player_reconnected,
    start_room,
)
from ..settings import PUBLIC_APP_URL
from ..xiangqi import (
    GameStatus,
    Move,
    Side,
    XiangqiState,
    apply_move,
    game_status,
    game_winner,
    legal_moves,
)


logger = logging.getLogger(__name__)
router = APIRouter()


def _service_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Room service is temporarily unavailable",
    )


def _room_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Room not found",
    )


def _join_url(room_id: int, invite_token: str) -> str:
    query = urlencode({"token": invite_token})
    return f"{PUBLIC_APP_URL}/room/{room_id}?{query}"


def _access_response(
    room: dict[str, Any],
    role: str,
    participant_token: str,
) -> RoomAccessResponse:
    try:
        invite_token = get_or_create_invite_token(room["id"])
    except RedisError as exc:
        logger.exception("Could not read invite token for room %s", room["id"])
        raise _service_unavailable() from exc
    if invite_token is None:
        raise _room_not_found()

    return RoomAccessResponse(
        **room,
        role=role,
        participant_token=participant_token,
        join_url=_join_url(room["id"], invite_token),
    )


def _room_summary(room_id: int) -> dict[str, Any] | None:
    try:
        return get_room(room_id)
    except RedisError as exc:
        logger.exception("Could not read room %s from Redis", room_id)
        raise _service_unavailable() from exc


def _process_room_move(
    room_id: int,
    role: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    """Validate, atomically store, and serialize one client-requested move."""
    if role not in {"player1", "player2"}:
        return {"type": "move_rejected", "reason": "spectators_cannot_move"}

    try:
        request = RoomMoveRequest.model_validate(message)
    except ValidationError:
        return {"type": "move_rejected", "reason": "invalid_move_payload"}

    try:
        snapshot = get_game_snapshot(room_id)
    except RedisError as exc:
        logger.exception("Could not load game state for room %s", room_id)
        return {"type": "move_rejected", "reason": "game_service_unavailable"}
    if snapshot is None or snapshot["status"] != "playing":
        return {"type": "move_rejected", "reason": "game_not_playing"}
    if snapshot["paused"]:
        return {
            "type": "move_rejected",
            "reason": "player_disconnected",
            "game": snapshot,
        }

    moving_side = Side.RED if role == "player1" else Side.BLACK
    if snapshot["side_to_move"] != moving_side.value:
        return {"type": "move_rejected", "reason": "not_your_turn", "game": snapshot}

    try:
        state = XiangqiState.from_fen(snapshot["fen"])
        move = Move(request.from_square, request.to_square)
    except ValueError:
        logger.exception("Stored game state or move coordinates are invalid for room %s", room_id)
        return {"type": "move_rejected", "reason": "invalid_move_payload"}

    if move not in legal_moves(state):
        return {"type": "move_rejected", "reason": "illegal_move", "game": snapshot}

    next_state = apply_move(state, move)
    status_after_move = game_status(next_state)
    terminal = status_after_move not in {GameStatus.ACTIVE, GameStatus.CHECK}
    winner = game_winner(next_state) if terminal else None
    result = status_after_move.value if terminal else None

    try:
        update_result = apply_game_move(
            room_id=room_id,
            expected_version=snapshot["version"],
            expected_fen=snapshot["fen"],
            moving_side=moving_side.value,
            next_side=next_state.turn.value,
            next_fen=next_state.to_fen(),
            result=result,
            winner=winner.value if winner is not None else None,
        )
        latest_snapshot = get_game_snapshot(room_id)
    except RedisError as exc:
        logger.exception("Could not apply move for room %s", room_id)
        return {"type": "move_rejected", "reason": "game_service_unavailable"}

    if update_result == -3:
        if latest_snapshot is None:
            return {"type": "move_rejected", "reason": "game_not_playing"}
        return {"type": "game.timeout", "room_id": room_id, "game": latest_snapshot}
    if update_result == -2:
        return {
            "type": "move_rejected",
            "reason": "stale_position",
            "game": latest_snapshot,
        }
    if update_result != 1 or latest_snapshot is None:
        return {"type": "move_rejected", "reason": "game_not_playing"}

    return {
        "type": "move_made",
        "room_id": room_id,
        "move": {"from": list(move.origin), "to": list(move.destination)},
        "game": latest_snapshot,
    }


@router.post(
    "/",
    response_model=RoomAccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a public room",
)
def create_public_room(
    payload: RoomCreateRequest,
    background_tasks: BackgroundTasks,
) -> RoomAccessResponse:
    """Create a public lobby room and assign its creator player one."""
    try:
        room, host_token = create_room(
            payload.name,
            payload.host_name,
            payload.timer_seconds,
        )
    except RedisError as exc:
        logger.exception("Could not create a room in Redis")
        raise _service_unavailable() from exc

    background_tasks.add_task(
        room_hub.broadcast_lobby,
        {"type": "room.created", "room": room},
    )
    return _access_response(room, "player1", host_token)


@router.get(
    "/",
    response_model=list[RoomSummary],
    summary="List public rooms waiting for an opponent",
)
def get_public_rooms() -> list[RoomSummary]:
    """List public rooms still waiting in the lobby."""
    try:
        rooms = list_public_rooms()
    except RedisError as exc:
        logger.exception("Could not list public rooms from Redis")
        raise _service_unavailable() from exc
    return [RoomSummary(**room) for room in rooms]


def _join_room_response(
    room_id: int,
    payload: RoomJoinRequest,
    background_tasks: BackgroundTasks,
) -> RoomAccessResponse:
    room = _room_summary(room_id)
    if room is None:
        raise _room_not_found()

    if payload.invite_token is not None:
        try:
            valid_invite = is_valid_invite_token(room_id, payload.invite_token)
        except RedisError as exc:
            logger.exception("Could not validate invitation for room %s", room_id)
            raise _service_unavailable() from exc
        if not valid_invite:
            raise HTTPException(status_code=403, detail="The room invitation link is invalid")

    participant_token = payload.participant_token or secrets.token_urlsafe(32)
    try:
        role = join_room(room_id, participant_token)
    except RedisError as exc:
        logger.exception("Could not join room %s in Redis", room_id)
        raise _service_unavailable() from exc

    if role is None:
        raise _room_not_found()

    room = _room_summary(room_id)
    if room is None:
        raise _room_not_found()

    background_tasks.add_task(
        room_hub.broadcast_room,
        room_id,
        {"type": "room.participant_joined", "role": role, "room": room},
    )
    if room["status"] == "waiting":
        background_tasks.add_task(
            room_hub.broadcast_lobby,
            {"type": "room.updated", "room": room},
        )
    return _access_response(room, role, participant_token)


@router.post(
    "/join",
    response_model=RoomAccessResponse,
    summary="Join a public room using its numeric room code",
)
def join_room_by_code(
    payload: RoomCodeJoinRequest,
    background_tasks: BackgroundTasks,
) -> RoomAccessResponse:
    """Resolve a lobby-entered room code and join that public room."""
    return _join_room_response(
        int(payload.room_code),
        RoomJoinRequest(
            participant_token=payload.participant_token,
            invite_token=payload.invite_token,
        ),
        background_tasks,
    )


@router.get(
    "/{room_id}",
    response_model=RoomSummary,
    summary="Get room details by shareable room ID",
)
def get_room_details(room_id: int) -> RoomSummary:
    """Return a room's public details for a direct invitation link."""
    room = _room_summary(room_id)
    if room is None:
        raise _room_not_found()
    return RoomSummary(**room)


@router.get(
    "/{room_id}/game",
    response_model=RoomGameSnapshot,
    summary="Get the current server-authoritative board and clocks",
)
def get_room_game_state(room_id: int) -> RoomGameSnapshot:
    """Return the current FEN, side to move, version, and remaining clocks."""
    room = _room_summary(room_id)
    if room is None:
        raise _room_not_found()
    if room["status"] == "waiting":
        raise HTTPException(status_code=409, detail="The game has not started")
    try:
        game = get_game_snapshot(room_id)
    except RedisError as exc:
        logger.exception("Could not load game state for room %s", room_id)
        raise _service_unavailable() from exc
    if game is None:
        raise HTTPException(status_code=409, detail="The game state is unavailable")
    return RoomGameSnapshot(**game)


@router.post(
    "/{room_id}/join",
    response_model=RoomAccessResponse,
    summary="Join a room as a player or spectator",
)
def join_public_room(
    room_id: int,
    payload: RoomJoinRequest,
    background_tasks: BackgroundTasks,
) -> RoomAccessResponse:
    """Assign the second player slot or make the joiner a spectator."""
    return _join_room_response(room_id, payload, background_tasks)


@router.post(
    "/{room_id}/invite",
    response_model=RoomInviteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Email a friend a direct room invitation",
)
def email_room_invitation(
    room_id: int,
    payload: RoomInviteRequest,
) -> RoomInviteResponse:
    """Send the host's room link and numeric room code to a friend."""
    room = _room_summary(room_id)
    if room is None:
        raise _room_not_found()

    try:
        role = get_participant_role(room_id, payload.participant_token)
    except RedisError as exc:
        logger.exception("Could not validate room host for room %s", room_id)
        raise _service_unavailable() from exc

    if role != "player1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the room host can email invitations",
        )

    try:
        invite_token = get_or_create_invite_token(room_id)
    except RedisError as exc:
        logger.exception("Could not load invite link for room %s", room_id)
        raise _service_unavailable() from exc
    if invite_token is None:
        raise _room_not_found()

    join_url = _join_url(room_id, invite_token)
    try:
        send_room_invitation_email(
            recipient=str(payload.email),
            room_name=room["name"],
            room_code=str(room_id),
            join_url=join_url,
        )
    except EmailConfigurationError as exc:
        logger.exception("Room invitation email service is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        ) from exc
    except EmailDeliveryError as exc:
        logger.exception("Could not send room invitation for room %s", room_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not send invitation email",
        ) from exc

    return RoomInviteResponse(
        message="Invitation email sent",
        email=payload.email,
        room_code=str(room_id),
        join_url=join_url,
    )


@router.post(
    "/{room_id}/start",
    response_model=RoomSummary,
    summary="Start a room's game",
)
def start_public_room(
    room_id: int,
    payload: RoomActionRequest,
    background_tasks: BackgroundTasks,
) -> RoomSummary:
    """Let the host start play; started rooms disappear from the public list."""
    try:
        result = start_room(room_id, payload.participant_token)
    except RedisError as exc:
        logger.exception("Could not start room %s in Redis", room_id)
        raise _service_unavailable() from exc

    if result == -1:
        raise _room_not_found()
    if result == -2:
        raise HTTPException(status_code=403, detail="Only the room host can start the game")
    if result == -3:
        raise HTTPException(status_code=409, detail="The room has already started")
    if result == -4:
        raise HTTPException(status_code=409, detail="An opponent must join before the game starts")

    room = _room_summary(room_id)
    if room is None:
        raise _room_not_found()

    try:
        game = get_game_snapshot(room_id)
    except RedisError as exc:
        logger.exception("Could not load started game for room %s", room_id)
        raise _service_unavailable() from exc
    if game is None:
        raise HTTPException(status_code=503, detail="The game state was not initialized")

    background_tasks.add_task(room_hub.ensure_timer, room_id)
    background_tasks.add_task(
        room_hub.broadcast_lobby,
        {"type": "room.removed", "room_id": room_id, "reason": "started"},
    )
    background_tasks.add_task(
        room_hub.broadcast_room,
        room_id,
        {"type": "room.started", "room": room, "game": game},
    )
    return RoomSummary(**room)


@router.post(
    "/{room_id}/leave",
    response_model=RoomLeaveResponse,
    summary="Leave a room",
)
def leave_public_room(
    room_id: int,
    payload: RoomActionRequest,
    background_tasks: BackgroundTasks,
) -> RoomLeaveResponse:
    """Delete the room when its host leaves; otherwise remove or disconnect the participant."""
    try:
        result = leave_room(room_id, payload.participant_token)
    except RedisError as exc:
        logger.exception("Could not leave room %s in Redis", room_id)
        raise _service_unavailable() from exc

    if result == -1:
        raise _room_not_found()
    if result == -2:
        raise HTTPException(status_code=403, detail="The participant token is not valid for this room")
    if result == 2:
        background_tasks.add_task(room_hub.stop_room_timers, room_id)
        background_tasks.add_task(
            room_hub.broadcast_lobby,
            {"type": "room.removed", "room_id": room_id, "reason": "host_left"},
        )
        background_tasks.add_task(
            room_hub.broadcast_room,
            room_id,
            {"type": "room.closed", "room_id": room_id},
        )
        return RoomLeaveResponse(message="Room deleted", room_deleted=True)

    if result in {4, 5}:
        try:
            game = get_game_snapshot(room_id)
        except RedisError as exc:
            logger.exception("Could not read forfeited game %s", room_id)
            raise _service_unavailable() from exc
        if game is None:
            raise _room_not_found()
        loser_role = "player1" if result == 4 else "player2"
        event = {
            "type": "game.forfeit",
            "room_id": room_id,
            "reason": "player_left",
            "loser_role": loser_role,
            "game": game,
        }
        if result == 4:
            background_tasks.add_task(room_hub.close_after_forfeit, room_id, event)
            return RoomLeaveResponse(
                message="Host forfeited; room closed",
                room_deleted=True,
            )
        background_tasks.add_task(room_hub.publish_forfeit, room_id, event)
        return RoomLeaveResponse(
            message="Player forfeited; game finished",
            room_deleted=False,
        )

    room = _room_summary(room_id)
    if room is not None:
        background_tasks.add_task(
            room_hub.broadcast_room,
            room_id,
            {"type": "room.participant_left", "room": room},
        )
        if room["status"] == "waiting":
            background_tasks.add_task(
                room_hub.broadcast_lobby,
                {"type": "room.updated", "room": room},
            )
    return RoomLeaveResponse(message="Left room", room_deleted=False)


@router.websocket("/ws")
async def public_lobby_socket(websocket: WebSocket) -> None:
    """Stream public lobby changes to connected clients."""
    await room_hub.connect_lobby(websocket)
    logger.info("Lobby WebSocket connected", extra={"event": "websocket.lobby_connected"})
    try:
        rooms = await run_in_threadpool(list_public_rooms)
        await room_hub.send_to_client(websocket, {"type": "rooms.snapshot", "rooms": rooms})
        await room_hub.start_sender(websocket)
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await room_hub.send_to_client(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        pass
    except RedisError:
        logger.exception("Could not load public rooms for WebSocket client")
        await websocket.close(code=1011)
    finally:
        await room_hub.disconnect_lobby(websocket)
        logger.info("Lobby WebSocket disconnected", extra={"event": "websocket.lobby_disconnected"})


async def _handle_room_socket_disconnect(room_id: int, participant_token: str) -> None:
    """Apply host cleanup, waiting-seat removal, or reconnect grace after a drop."""
    try:
        result = await run_in_threadpool(
            mark_player_disconnected,
            room_id,
            participant_token,
        )
    except RedisError:
        logger.exception("Could not process room participant disconnect")
        return

    code = result["code"]
    role = result["role"]
    logger.info(
        "Room WebSocket disconnected",
        extra={
            "event": "websocket.disconnected",
            "room_id": room_id,
            "role": role,
            "outcome": code,
        },
    )
    if code == 2:
        await room_hub.stop_room_timers(room_id)
        await room_hub.broadcast_lobby(
            {"type": "room.removed", "room_id": room_id, "reason": "host_left"}
        )
        await room_hub.broadcast_room(
            room_id,
            {"type": "room.closed", "room_id": room_id},
        )
    elif code == 3:
        # Freeze the per-turn broadcaster before notifying peers so a blocked
        # timer tick cannot delay the disconnect event.
        await room_hub.stop_timer(room_id)
        await room_hub.schedule_reconnect_timeout(
            room_id,
            role,
            result["deadline_ms"],
            result["delay_ms"],
        )
        await room_hub.broadcast_room(
            room_id,
            {
                "type": "player.disconnected",
                "room_id": room_id,
                "role": role,
                "reconnect_deadline_ms": result["deadline_ms"],
                "reconnect_seconds": 60,
                "game_paused": True,
            },
        )
    elif code == 4:
        await room_hub.stop_room_timers(room_id)
        try:
            game = await run_in_threadpool(get_game_snapshot, room_id)
        except RedisError:
            logger.exception("Could not read timed-out game %s", room_id)
            game = None
        if game is not None:
            await room_hub.broadcast_room(
                room_id,
                {"type": "game.timeout", "room_id": room_id, "game": game},
            )
    elif code == 1:
        try:
            updated_room = await run_in_threadpool(get_room, room_id)
        except RedisError:
            logger.exception("Could not read room %s after participant disconnect", room_id)
            return
        if updated_room is not None:
            await room_hub.broadcast_room(
                room_id,
                {"type": "room.participant_left", "room": updated_room},
            )
            if updated_room["status"] == "waiting":
                await room_hub.broadcast_lobby(
                    {"type": "room.updated", "room": updated_room}
                )


@router.websocket("/{room_id}/ws")
async def room_socket(websocket: WebSocket, room_id: int) -> None:
    """Stream room state and lifecycle events to participants."""
    participant_token = websocket.query_params.get("participant_token", "")
    if not participant_token:
        logger.warning(
            "Room WebSocket authentication failed",
            extra={
                "event": "websocket.auth_failed",
                "room_id": room_id,
                "reason": "missing_participant_token",
            },
        )
        await websocket.close(code=4401, reason="participant_token is required")
        return

    try:
        role = await run_in_threadpool(get_participant_role, room_id, participant_token)
        room = await run_in_threadpool(get_room, room_id)
    except RedisError:
        logger.exception(
            "Could not validate room WebSocket credentials",
            extra={
                "event": "websocket.auth_validation_failed",
                "room_id": room_id,
                "reason": "redis_unavailable",
            },
        )
        await websocket.close(code=1011, reason="Room service is unavailable")
        return

    if room is None or role is None:
        logger.warning(
            "Room WebSocket authentication failed",
            extra={
                "event": "websocket.auth_failed",
                "room_id": room_id,
                "reason": "unknown_room_or_participant",
            },
        )
        await websocket.close(code=4404, reason="Room or participant token not found")
        return

    reconnected = False
    if role in {"player1", "player2"}:
        try:
            reconnect_result = await run_in_threadpool(
                mark_player_reconnected,
                room_id,
                role,
                participant_token,
            )
        except RedisError:
            logger.exception("Could not restore room player connection for room %s", room_id)
            await websocket.close(code=1011, reason="Room service is unavailable")
            return
        if reconnect_result in {-1, -2}:
            await websocket.close(code=4404, reason="Room or participant token not found")
            return
        if reconnect_result == -4:
            logger.warning(
                "Room WebSocket reconnect arrived after its deadline",
                extra={
                    "event": "websocket.reconnect_expired",
                    "room_id": room_id,
                    "role": role,
                },
            )
            await websocket.close(code=4409, reason="Reconnect window expired")
            return
        if reconnect_result == -3:
            logger.warning(
                "Room WebSocket reconnect arrived after its deadline",
                extra={
                    "event": "websocket.reconnect_expired",
                    "room_id": room_id,
                    "role": role,
                },
            )
            try:
                game = await run_in_threadpool(get_game_snapshot, room_id)
            except RedisError:
                logger.exception("Could not read expired reconnect game %s", room_id)
                await websocket.close(code=1011, reason="Room service is unavailable")
                return
            await room_hub.publish_forfeit(
                room_id,
                {
                    "type": "game.forfeit",
                    "room_id": room_id,
                    "reason": "reconnect_timeout",
                    "loser_role": role,
                    "game": game,
                },
            )
            await websocket.close(code=4409, reason="Reconnect window expired")
            return
        reconnected = reconnect_result == 1
        if reconnected:
            await room_hub.stop_reconnect_timeout(room_id, role)

    await room_hub.connect_room(room_id, websocket, participant_token)
    logger.info(
        "Room WebSocket connected",
        extra={
            "event": "websocket.connected",
            "worker_id": room_hub.health_status()["worker_id"],
            "room_id": room_id,
            "role": role,
        },
    )
    try:
        game = None
        if room["status"] in {"playing", "finished"}:
            game = await run_in_threadpool(get_game_snapshot, room_id)
        if room["status"] == "playing":
            await room_hub.ensure_timer(room_id)
        await room_hub.send_to_client(
            websocket,
            {"type": "room.snapshot", "room": room, "role": role, "game": game},
        )
        await room_hub.start_sender(websocket)
        if reconnected:
            await room_hub.broadcast_room(
                room_id,
                {
                    "type": "player.reconnected",
                    "room_id": room_id,
                    "role": role,
                    "game": game,
                },
            )
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await room_hub.send_to_client(websocket, {"type": "pong"})
            elif isinstance(message, dict) and message.get("type") == "make_move":
                event = await run_in_threadpool(
                    _process_room_move,
                    room_id,
                    role,
                    message,
                )
                if event["type"] in {"move_made", "game.timeout"}:
                    game_state = event.get("game")
                    if game_state is not None and game_state["status"] == "finished":
                        await room_hub.stop_timer(room_id)
                    await room_hub.broadcast_room(room_id, event)
                else:
                    await room_hub.send_to_client(websocket, event)
            else:
                await room_hub.send_to_client(
                    websocket,
                    {"type": "error", "reason": "unsupported_message"},
                )
    except WebSocketDisconnect:
        pass
    except (RuntimeError, RedisError):
        logger.exception(
            "Room WebSocket failed for room %s",
            room_id,
            extra={"event": "websocket.failed", "room_id": room_id, "role": role},
        )
    finally:
        await room_hub.disconnect_room(room_id, websocket)
        if not await room_hub.has_participant_connection(room_id, participant_token):
            await _handle_room_socket_disconnect(room_id, participant_token)
