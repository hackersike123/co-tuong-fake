"""Authorization for reading room metadata and live game state."""

from typing import Literal

from fastapi import HTTPException, status

from .room_store import get_participant_role, get_room_password_hash, is_valid_invite_token
from .security import verify_password

RoomReadAction = Literal["read_room", "read_game_state", "read_game_history"]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Room access credentials are required",
    )


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Room access is not authorized",
    )


def _authorize_guest(room: dict, action: RoomReadAction) -> str:
    if action != "read_room" and not room["allow_spectators"]:
        raise _forbidden()
    return "invited"


def authorize_room_access(
    room: dict,
    action: RoomReadAction,
    *,
    participant_token: str | None = None,
    invite_token: str | None = None,
    password: str | None = None,
) -> str:
    """Authorize a read using server-verified room credentials.

    Participant roles come only from the room's Redis mapping. Invite and
    password credentials provide guest access to room details; game state and
    history treat guests as spectators and enforce the room's spectator policy.
    """
    room_id = int(room["id"])

    if participant_token:
        role = get_participant_role(room_id, participant_token)
        if role in {"player1", "player2"}:
            return role
        if role == "spectator" and room["allow_spectators"]:
            return role
        raise _forbidden()

    if invite_token:
        if not is_valid_invite_token(room_id, invite_token):
            raise _forbidden()
        return _authorize_guest(room, action)

    if password:
        password_hash = get_room_password_hash(room_id)
        if password_hash is None or not verify_password(password, password_hash):
            raise _forbidden()
        return _authorize_guest(room, action)

    if room["is_public"] and not room["has_password"]:
        if action == "read_room":
            return "public"
        if room["allow_spectators"]:
            return "spectator"

    raise _unauthorized()
