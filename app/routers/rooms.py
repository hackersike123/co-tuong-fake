"""Create, join, start, leave, and observe public game rooms."""

import logging
import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect, status
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from ..room_hub import room_hub
from ..room_schemas import (
    RoomAccessResponse,
    RoomActionRequest,
    RoomCreateRequest,
    RoomJoinRequest,
    RoomLeaveResponse,
    RoomSummary,
)
from ..room_store import (
    create_room,
    get_participant_role,
    get_room,
    join_room,
    leave_room,
    list_public_rooms,
    start_room,
)
from ..settings import PUBLIC_APP_URL


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


def _join_url(room_id: int) -> str:
    return f"{PUBLIC_APP_URL}/rooms/{room_id}"


def _access_response(
    room: dict[str, Any],
    role: str,
    participant_token: str,
) -> RoomAccessResponse:
    return RoomAccessResponse(
        **room,
        role=role,
        participant_token=participant_token,
        join_url=_join_url(room["id"]),
    )


def _room_summary(room_id: int) -> dict[str, Any] | None:
    try:
        return get_room(room_id)
    except RedisError as exc:
        logger.exception("Could not read room %s from Redis", room_id)
        raise _service_unavailable() from exc


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
        room, host_token = create_room(payload.name)
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

    background_tasks.add_task(
        room_hub.broadcast_lobby,
        {"type": "room.removed", "room_id": room_id, "reason": "started"},
    )
    background_tasks.add_task(
        room_hub.broadcast_room,
        room_id,
        {"type": "room.started", "room": room},
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
    message = "Player disconnected; their seat can reconnect" if result == 3 else "Left room"
    return RoomLeaveResponse(message=message, room_deleted=False)


@router.websocket("/ws")
async def public_lobby_socket(websocket: WebSocket) -> None:
    """Stream public lobby changes to connected clients."""
    await room_hub.connect_lobby(websocket)
    try:
        rooms = await run_in_threadpool(list_public_rooms)
        await websocket.send_json({"type": "rooms.snapshot", "rooms": rooms})
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except RedisError:
        logger.exception("Could not load public rooms for WebSocket client")
        await websocket.close(code=1011)
    finally:
        await room_hub.disconnect_lobby(websocket)


@router.websocket("/{room_id}/ws")
async def room_socket(websocket: WebSocket, room_id: int) -> None:
    """Stream room state and lifecycle events to participants."""
    participant_token = websocket.query_params.get("participant_token", "")
    if not participant_token:
        await websocket.close(code=4401, reason="participant_token is required")
        return

    try:
        role = await run_in_threadpool(get_participant_role, room_id, participant_token)
        room = await run_in_threadpool(get_room, room_id)
    except RedisError:
        logger.exception("Could not validate room WebSocket credentials")
        await websocket.close(code=1011, reason="Room service is unavailable")
        return

    if room is None or role is None:
        await websocket.close(code=4404, reason="Room or participant token not found")
        return

    await room_hub.connect_room(room_id, websocket)
    try:
        await websocket.send_json({"type": "room.snapshot", "room": room, "role": role})
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except (RuntimeError, RedisError):
        logger.exception("Room WebSocket failed for room %s", room_id)
    finally:
        await room_hub.disconnect_room(room_id, websocket)
        try:
            result = await run_in_threadpool(leave_room, room_id, participant_token)
        except RedisError:
            logger.exception("Could not process room participant disconnect")
        else:
            if result == 2:
                await room_hub.broadcast_lobby(
                    {"type": "room.removed", "room_id": room_id, "reason": "host_left"}
                )
                await room_hub.broadcast_room(
                    room_id,
                    {"type": "room.closed", "room_id": room_id},
                )
            elif result in (1, 3):
                updated_room = await run_in_threadpool(get_room, room_id)
                if updated_room is not None:
                    await room_hub.broadcast_room(
                        room_id,
                        {"type": "room.participant_left", "room": updated_room},
                    )
                    if updated_room["status"] == "waiting":
                        await room_hub.broadcast_lobby(
                            {"type": "room.updated", "room": updated_room}
                        )
