"""Authorization for room details, live state, and saved room history."""

import hashlib
import json
import secrets
from collections.abc import Sequence
from typing import Literal

from fastapi import HTTPException, status

from .room_store import get_participant_role, get_room_password_hash, is_valid_invite_token
from .security import verify_password

RoomReadAction = Literal["read_room", "read_game_state", "read_game_history"]


def hash_room_token(token: str) -> str:
    """Hash a room bearer token before persisting it with match history."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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


def authorize_archived_room_history(
    matches: Sequence[object],
    *,
    participant_token: str | None = None,
) -> list[object]:
    """Authorize history after the Redis room has been removed.

    Match records retain only hashes of credentials that were valid in that
    room. Historical access is read-only and never authorizes live room access.
    """
    if participant_token:
        digest = hash_room_token(participant_token)
        authorized_matches: list[object] = []
        for match in matches:
            try:
                token_roles = json.loads(getattr(match, "access_token_hashes", "{}"))
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(token_roles, dict):
                continue
            role_for_match: str | None = None
            for stored_hash, role in token_roles.items():
                if isinstance(stored_hash, str) and secrets.compare_digest(stored_hash, digest):
                    role_for_match = str(role)
                    break
            if role_for_match in {"player1", "player2"} or (
                role_for_match == "spectator"
                and bool(getattr(match, "allow_spectators", False))
            ):
                authorized_matches.append(match)
        if authorized_matches:
            return authorized_matches
        raise _forbidden()

    public_matches = [
        match
        for match in matches
        if bool(getattr(match, "is_public", False))
        and not bool(getattr(match, "has_password", False))
        and bool(getattr(match, "allow_spectators", False))
    ]
    if public_matches:
        return public_matches

    raise _unauthorized()
