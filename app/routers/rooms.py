"""Create, join, start, leave, and observe public game rooms."""

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from ..email_service import (
    EmailConfigurationError,
    EmailDeliveryError,
    send_room_invitation_email,
)
from ..match_service import list_match_history, match_payload, record_completed_match
from ..room_hub import room_hub
from ..room_access import authorize_room_access
from ..room_schemas import (
    RoomAccessResponse,
    RoomActionRequest,
    RoomCodeJoinRequest,
    RoomCreateRequest,
    RoomInviteRequest,
    RoomInviteResponse,
    RoomGameSnapshot,
    RoomMatchHistory,
    RoomJoinRequest,
    RoomReadyRequest,
    RoomLeaveResponse,
    RoomMoveRequest,
    RoomSummary,
)
from ..room_store import (
    create_room,
    apply_game_move,
    get_participant_role,
    get_room,
    get_room_password_hash,
    get_game_snapshot,
    get_or_create_invite_token,
    is_valid_invite_token,
    join_room,
    leave_room,
    list_public_rooms,
    mark_player_disconnected,
    mark_player_reconnected,
    set_player_ready,
    start_room,
    offer_draw,
    respond_to_draw,
    resign_game,
    request_rematch,
)
from ..security import hash_password, verify_password
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


def _update_player_ready(
    room_id: int,
    participant_token: str,
    ready: bool,
) -> dict[str, Any]:
    """Set player two's readiness, preserving Redis-backed role validation."""
    try:
        result = set_player_ready(room_id, participant_token, ready)
    except RedisError as exc:
        logger.exception("Could not update ready state for room %s", room_id)
        raise _service_unavailable() from exc

    if result == -1:
        raise _room_not_found()
    if result == -2:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only player two can change the ready state",
        )
    if result == -3:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The room is no longer waiting",
        )

    room = _room_summary(room_id)
    if room is None:
        raise _room_not_found()
    return room


def _game_over_event(room_id: int, game: dict[str, Any]) -> dict[str, Any]:
    """Build the common terminal event used by every completed game round."""
    return {
        "type": "game_over",
        "room_id": room_id,
        "result": game.get("result"),
        "reason": game.get("reason") or game.get("result"),
        "winner": game.get("winner"),
        "notation": game.get("notation", ""),
        "game": game,
    }


def _move_notation(snapshot: dict[str, Any], move: Move, side: Side) -> str:
    """Format the server-accepted move in coordinate notation (for example b9-a7)."""
    files = "abcdefghi"

    def square_name(square: tuple[int, int]) -> str:
        row, column = square
        return f"{files[column]}{row}"

    move_number = snapshot["version"] // 2 + 1
    prefix = f"{move_number}." if side is Side.RED else f"{move_number}..."
    return f"{prefix} {square_name(move.origin)}-{square_name(move.destination)}"


def _room_action_error(result: int, action: str) -> dict[str, Any] | None:
    """Map the Redis lifecycle script's negative statuses to a socket error."""
    errors = {
        -1: "room_not_found",
        -2: "player_required",
        -3: "game_not_playing" if action != "rematch" else "game_not_finished",
        -4: "draw_offer_pending" if action == "offer_draw" else "no_pending_draw_offer",
    }
    if result >= 0:
        return None
    return {"type": "error", "reason": errors.get(result, "invalid_game_action")}


def _process_offer_draw(
    room_id: int, role: str, participant_token: str
) -> dict[str, Any]:
    if role not in {"player1", "player2"}:
        return {"type": "error", "reason": "players_only"}
    try:
        result = offer_draw(room_id, participant_token, role)
        game = get_game_snapshot(room_id)
    except RedisError:
        logger.exception("Could not offer a draw in room %s", room_id)
        return {"type": "error", "reason": "game_service_unavailable"}
    error = _room_action_error(result, "offer_draw")
    if error:
        return error
    if game is None:
        return {"type": "error", "reason": "game_not_playing"}
    return {"type": "draw_offered", "room_id": room_id, "role": role, "game": game}


def _process_draw_response(
    room_id: int,
    role: str,
    participant_token: str,
    accept: bool,
) -> dict[str, Any]:
    if role not in {"player1", "player2"}:
        return {"type": "error", "reason": "players_only"}
    try:
        result = respond_to_draw(room_id, participant_token, role, accept)
        game = get_game_snapshot(room_id)
    except RedisError:
        logger.exception("Could not respond to a draw offer in room %s", room_id)
        return {"type": "error", "reason": "game_service_unavailable"}
    if result == 2:
        if game is None:
            return {"type": "error", "reason": "game_not_playing"}
        record_completed_match(room_id)
        return _game_over_event(room_id, game)
    if result == 1:
        return {"type": "draw_declined", "room_id": room_id, "role": role, "game": game}
    error = _room_action_error(result, "respond_draw")
    return error or {"type": "error", "reason": "no_pending_draw_offer"}


def _process_resignation(
    room_id: int, role: str, participant_token: str
) -> dict[str, Any]:
    if role not in {"player1", "player2"}:
        return {"type": "error", "reason": "players_only"}
    try:
        result = resign_game(room_id, participant_token, role)
        game = get_game_snapshot(room_id)
    except RedisError:
        logger.exception("Could not resign game in room %s", room_id)
        return {"type": "error", "reason": "game_service_unavailable"}
    if result == 1 and game is not None:
        record_completed_match(room_id)
        return _game_over_event(room_id, game)
    error = _room_action_error(result, "resign")
    return error or {"type": "error", "reason": "game_not_playing"}


def _process_rematch(
    room_id: int, role: str, participant_token: str
) -> dict[str, Any]:
    if role not in {"player1", "player2"}:
        return {"type": "error", "reason": "players_only"}
    try:
        result = request_rematch(room_id, participant_token, role)
        room = get_room(room_id)
    except RedisError:
        logger.exception("Could not request a rematch in room %s", room_id)
        return {"type": "error", "reason": "game_service_unavailable"}
    error = _room_action_error(result, "rematch")
    if error:
        return error
    if result == 2:
        if room is None:
            return {"type": "error", "reason": "room_not_found"}
        return {"type": "room.rematch_started", "room": room}
    return {"type": "room.rematch_requested", "room_id": room_id, "role": role}


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
            notation=_move_notation(snapshot, move, moving_side),
            reason=status_after_move.value if terminal else None,
        )
        latest_snapshot = get_game_snapshot(room_id)
    except RedisError as exc:
        logger.exception("Could not apply move for room %s", room_id)
        return {"type": "move_rejected", "reason": "game_service_unavailable"}

    if update_result == -3:
        if latest_snapshot is None:
            return {"type": "move_rejected", "reason": "game_not_playing"}
        record_completed_match(room_id)
        return {
            "type": "game.timeout",
            "room_id": room_id,
            "game": latest_snapshot,
            "game_over": _game_over_event(room_id, latest_snapshot),
        }
    if update_result == -2:
        return {
            "type": "move_rejected",
            "reason": "stale_position",
            "game": latest_snapshot,
        }
    if update_result != 1 or latest_snapshot is None:
        return {"type": "move_rejected", "reason": "game_not_playing"}

    event = {
        "type": "move_made",
        "room_id": room_id,
        "move": {"from": list(move.origin), "to": list(move.destination)},
        "game": latest_snapshot,
    }
    if terminal:
        record_completed_match(room_id)
        event["game_over"] = _game_over_event(room_id, latest_snapshot)
    return event


@router.post(
    "/",
    response_model=RoomAccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a public or private room",
)
def create_public_room(
    payload: RoomCreateRequest,
    background_tasks: BackgroundTasks,
) -> RoomAccessResponse:
    """Create a room and assign its creator player one."""
    password_hash = hash_password(payload.password) if payload.password is not None else None
    try:
        room, host_token = create_room(
            payload.room_name,
            payload.host_name,
            payload.time_per_move,
            is_public=payload.is_public,
            password_hash=password_hash,
            allow_spectators=payload.allow_spectators,
        )
    except RedisError as exc:
        logger.exception("Could not create a room in Redis")
        raise _service_unavailable() from exc

    if room["is_public"]:
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

    valid_invite = False
    if payload.invite_token is not None:
        try:
            valid_invite = is_valid_invite_token(room_id, payload.invite_token)
        except RedisError as exc:
            logger.exception("Could not validate invitation for room %s", room_id)
            raise _service_unavailable() from exc
        if not valid_invite:
            raise HTTPException(status_code=403, detail="The room invitation link is invalid")

    existing_participant = False
    if (
        (room["has_password"] or not room["is_public"])
        and not valid_invite
        and payload.participant_token is not None
    ):
        try:
            existing_participant = (
                get_participant_role(room_id, payload.participant_token) is not None
            )
        except RedisError as exc:
            logger.exception("Could not validate room participant for room %s", room_id)
            raise _service_unavailable() from exc

    if (
        (room["has_password"] or not room["is_public"])
        and not valid_invite
        and not existing_participant
    ):
        try:
            password_hash = get_room_password_hash(room_id)
        except RedisError as exc:
            logger.exception("Could not load room password for room %s", room_id)
            raise _service_unavailable() from exc
        if (
            payload.password is None
            or password_hash is None
            or not verify_password(payload.password, password_hash)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A valid room password or invitation link is required",
            )

    participant_token = payload.participant_token or secrets.token_urlsafe(32)
    try:
        role = join_room(room_id, participant_token)
    except RedisError as exc:
        logger.exception("Could not join room %s in Redis", room_id)
        raise _service_unavailable() from exc

    if role is None:
        raise _room_not_found()
    if role == "spectators_disabled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Spectators are not allowed in this room",
        )

    room = _room_summary(room_id)
    if room is None:
        raise _room_not_found()

    background_tasks.add_task(
        room_hub.broadcast_room,
        room_id,
        {"type": "room.participant_joined", "role": role, "room": room},
    )
    if room["is_public"] and room["status"] == "waiting":
        background_tasks.add_task(
            room_hub.broadcast_lobby,
            {"type": "room.updated", "room": room},
        )
    return _access_response(room, role, participant_token)


@router.post(
    "/join",
    response_model=RoomAccessResponse,
    summary="Join a room using its numeric room code",
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
            password=payload.password,
        ),
        background_tasks,
    )


@router.get(
    "/{room_id}",
    response_model=RoomSummary,
    summary="Get room details by shareable room ID",
)
def get_room_details(
    room_id: int,
    participant_token: str | None = Header(default=None, alias="X-Room-Participant-Token"),
    invite_token: str | None = Header(default=None, alias="X-Room-Invite-Token"),
    password: str | None = Header(default=None, alias="X-Room-Password"),
) -> RoomSummary:
    """Return a room's public details for a direct invitation link."""
    room = _room_summary(room_id)
    if room is None:
        raise _room_not_found()
    try:
        authorize_room_access(
            room,
            "read_room",
            participant_token=participant_token,
            invite_token=invite_token,
            password=password,
        )
    except RedisError as exc:
        logger.exception("Could not validate read access for room %s", room_id)
        raise _service_unavailable() from exc
    return RoomSummary(**room)


@router.get(
    "/{room_id}/game",
    response_model=RoomGameSnapshot,
    summary="Get the current server-authoritative board and clocks",
)
def get_room_game_state(
    room_id: int,
    participant_token: str | None = Header(default=None, alias="X-Room-Participant-Token"),
    invite_token: str | None = Header(default=None, alias="X-Room-Invite-Token"),
    password: str | None = Header(default=None, alias="X-Room-Password"),
) -> RoomGameSnapshot:
    """Return the current FEN, side to move, version, and remaining clocks."""
    room = _room_summary(room_id)
    if room is None:
        raise _room_not_found()
    try:
        authorize_room_access(
            room,
            "read_game_state",
            participant_token=participant_token,
            invite_token=invite_token,
            password=password,
        )
    except RedisError as exc:
        logger.exception("Could not validate game-state access for room %s", room_id)
        raise _service_unavailable() from exc
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


@router.get(
    "/{room_id}/matches",
    response_model=list[RoomMatchHistory],
    summary="Read completed game history for a room",
)
def get_room_match_history(room_id: int) -> list[RoomMatchHistory]:
    """Return the newest saved match records, even if the room has closed."""
    try:
        matches = list_match_history(room_id)
    except SQLAlchemyError as exc:
        logger.exception("Could not load match history for room %s", room_id)
        raise _service_unavailable() from exc
    return [RoomMatchHistory(**match_payload(match)) for match in matches]


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
    "/{room_id}/ready",
    response_model=RoomSummary,
    summary="Set player two's ready state",
)
def ready_room_player(
    room_id: int,
    payload: RoomReadyRequest,
    background_tasks: BackgroundTasks,
) -> RoomSummary:
    """Let only player two change readiness before the host starts the game."""
    room = _update_player_ready(room_id, payload.participant_token, payload.ready)
    event = {
        "type": "player.ready",
        "room": room,
        "role": "player2",
        "ready": payload.ready,
    }
    background_tasks.add_task(room_hub.broadcast_room, room_id, event)
    if room["is_public"]:
        background_tasks.add_task(
            room_hub.broadcast_lobby,
            {"type": "room.updated", "room": room},
        )
    return RoomSummary(**room)


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
    if result == -5:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Player two must be ready before the game starts",
        )

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
    if room["is_public"]:
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
    room_before_leave = _room_summary(room_id)
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
        if room_before_leave is not None and room_before_leave["is_public"]:
            background_tasks.add_task(
                room_hub.broadcast_lobby,
                {"type": "room.removed", "room_id": room_id, "reason": "host_left"},
            )
        background_tasks.add_task(
            room_hub.revoke_participant,
            room_id,
            payload.participant_token,
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
        record_completed_match(room_id)
        loser_role = "player1" if result == 4 else "player2"
        event = {
            "type": "game.forfeit",
            "room_id": room_id,
            "reason": "player_left",
            "loser_role": loser_role,
            "game": game,
        }
        if result == 4:
            background_tasks.add_task(
                room_hub.close_after_forfeit,
                room_id,
                event,
                payload.participant_token,
            )
            return RoomLeaveResponse(
                message="Host forfeited; room closed",
                room_deleted=True,
            )
        background_tasks.add_task(
            room_hub.publish_forfeit,
            room_id,
            event,
            payload.participant_token,
        )
        return RoomLeaveResponse(
            message="Player forfeited; game finished",
            room_deleted=False,
        )

    room = _room_summary(room_id)
    if room is not None:
        background_tasks.add_task(
            room_hub.revoke_participant,
            room_id,
            payload.participant_token,
        )
        background_tasks.add_task(
            room_hub.broadcast_room,
            room_id,
            {"type": "room.participant_left", "room": room},
        )
        if room["is_public"] and room["status"] == "waiting":
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
            elif isinstance(message, dict) and message.get("type") == "join_room":
                try:
                    requested_room_id = message.get("room_id")
                    if isinstance(requested_room_id, bool) or not isinstance(
                        requested_room_id, (int, str)
                    ):
                        raise ValueError("room_id must be an integer")
                    room_id = int(requested_room_id)
                    if room_id <= 0:
                        raise ValueError("room_id must be positive")
                    join_payload = RoomJoinRequest.model_validate(message)
                    background_tasks = BackgroundTasks()
                    access = _join_room_response(room_id, join_payload, background_tasks)
                    await background_tasks()
                except (TypeError, ValueError, ValidationError):
                    await room_hub.send_to_client(
                        websocket,
                        {"type": "error", "status": 422, "reason": "invalid_join_payload"},
                    )
                except HTTPException as exc:
                    await room_hub.send_to_client(
                        websocket,
                        {
                            "type": "error",
                            "status": exc.status_code,
                            "reason": exc.detail,
                        },
                    )
                else:
                    await room_hub.send_to_client(
                        websocket,
                        {"type": "room.joined", "access": access.model_dump(mode="json")},
                    )
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
            record_completed_match(room_id)
            await room_hub.broadcast_room(
                room_id,
                {"type": "game.timeout", "room_id": room_id, "game": game},
            )
            await room_hub.broadcast_room(room_id, _game_over_event(room_id, game))
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
            if updated_room["is_public"] and updated_room["status"] == "waiting":
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
    if role == "spectator" and not room["allow_spectators"]:
        logger.warning(
            "Room WebSocket rejected a spectator against room policy",
            extra={"event": "websocket.auth_failed", "room_id": room_id, "reason": "spectators_disabled"},
        )
        await websocket.close(code=4403, reason="Spectators are not allowed in this room")
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
            await run_in_threadpool(record_completed_match, room_id)
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
            elif isinstance(message, dict) and message.get("type") == "ready":
                ready = message.get("ready", True)
                if not isinstance(ready, bool):
                    await room_hub.send_to_client(
                        websocket,
                        {"type": "error", "reason": "invalid_ready_payload"},
                    )
                    continue
                try:
                    updated_room = await run_in_threadpool(
                        _update_player_ready,
                        room_id,
                        participant_token,
                        ready,
                    )
                except HTTPException as exc:
                    await room_hub.send_to_client(
                        websocket,
                        {
                            "type": "error",
                            "status": exc.status_code,
                            "reason": exc.detail,
                        },
                    )
                    continue
                await room_hub.broadcast_room(
                    room_id,
                    {
                        "type": "player.ready",
                        "room": updated_room,
                        "role": "player2",
                        "ready": ready,
                    },
                )
                if updated_room["is_public"]:
                    await room_hub.broadcast_lobby(
                        {"type": "room.updated", "room": updated_room}
                    )
            elif isinstance(message, dict) and message.get("type") == "make_move":
                event = await run_in_threadpool(
                    _process_room_move,
                    room_id,
                    role,
                    message,
                )
                game_over = event.pop("game_over", None)
                if event["type"] in {"move_made", "game.timeout"}:
                    game_state = event.get("game")
                    if game_state is not None and game_state["status"] == "finished":
                        await room_hub.stop_timer(room_id)
                    await room_hub.broadcast_room(room_id, event)
                    if game_over is not None:
                        await room_hub.broadcast_room(room_id, game_over)
                else:
                    await room_hub.send_to_client(websocket, event)
            elif isinstance(message, dict) and message.get("type") == "offer_draw":
                event = await run_in_threadpool(
                    _process_offer_draw,
                    room_id,
                    role,
                    participant_token,
                )
                if event["type"] == "error":
                    await room_hub.send_to_client(websocket, event)
                else:
                    await room_hub.broadcast_room(room_id, event)
            elif isinstance(message, dict) and message.get("type") == "respond_draw":
                accept = message.get("accept")
                if not isinstance(accept, bool):
                    await room_hub.send_to_client(
                        websocket,
                        {"type": "error", "reason": "invalid_draw_response"},
                    )
                    continue
                event = await run_in_threadpool(
                    _process_draw_response,
                    room_id,
                    role,
                    participant_token,
                    accept,
                )
                if event["type"] == "error":
                    await room_hub.send_to_client(websocket, event)
                else:
                    if event["type"] == "game_over":
                        await room_hub.stop_timer(room_id)
                    await room_hub.broadcast_room(room_id, event)
            elif isinstance(message, dict) and message.get("type") == "resign":
                event = await run_in_threadpool(
                    _process_resignation,
                    room_id,
                    role,
                    participant_token,
                )
                if event["type"] == "error":
                    await room_hub.send_to_client(websocket, event)
                else:
                    await room_hub.stop_timer(room_id)
                    await room_hub.broadcast_room(room_id, event)
            elif isinstance(message, dict) and message.get("type") == "rematch":
                event = await run_in_threadpool(
                    _process_rematch,
                    room_id,
                    role,
                    participant_token,
                )
                if event["type"] == "error":
                    await room_hub.send_to_client(websocket, event)
                else:
                    await room_hub.broadcast_room(room_id, event)
                    if (
                        event["type"] == "room.rematch_started"
                        and event["room"]["is_public"]
                    ):
                        await room_hub.broadcast_lobby(
                            {"type": "room.created", "room": event["room"]}
                        )
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
