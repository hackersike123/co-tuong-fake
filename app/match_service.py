"""Persistence helpers for completed room games."""

import json
import logging
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .database import SessionLocal
from .models import Match
from .room_access import hash_room_token
from .room_store import get_game_snapshot, get_room, get_room_participant_roles


logger = logging.getLogger(__name__)


def record_completed_match(
    room_id: int,
    *,
    additional_access_tokens: dict[str, str] | None = None,
) -> Match | None:
    """Persist one finished round; duplicate event delivery is safe to retry."""
    try:
        room = get_room(room_id)
        game = get_game_snapshot(room_id)
        if room is None or game is None or game["status"] != "finished":
            return None

        participant_tokens = get_room_participant_roles(room_id)
        if additional_access_tokens:
            participant_tokens.update(additional_access_tokens)
        access_token_hashes = {
            hash_room_token(token): role
            for token, role in participant_tokens.items()
            if role in {"player1", "player2", "spectator"}
        }

        round_number = int(game.get("round_number") or 1)
        match_key = f"{room['room_uuid']}:{round_number}"
        with SessionLocal() as session:
            existing = session.scalar(
                select(Match).where(Match.match_key == match_key)
            )
            if existing is not None:
                return existing

            match = Match(
                match_key=match_key,
                room_id=room_id,
                room_uuid=room["room_uuid"],
                round_number=round_number,
                room_name=room["room_name"],
                red_player=room["host_name"],
                black_player="Player 2",
                result=game.get("result") or "unknown",
                reason=game.get("reason"),
                winner=game.get("winner"),
                notation=game.get("notation", ""),
                final_fen=game["fen"],
                is_public=room["is_public"],
                has_password=room["has_password"],
                allow_spectators=room["allow_spectators"],
                access_token_hashes=json.dumps(access_token_hashes, separators=(",", ":")),
            )
            session.add(match)
            try:
                session.commit()
            except IntegrityError:
                # A different worker may have persisted the same round after
                # receiving the same terminal event at the same time.
                session.rollback()
                existing = session.scalar(
                    select(Match).where(Match.match_key == match_key)
                )
                if existing is None:
                    raise
                return existing
            session.refresh(match)
            return match
    except (RedisError, SQLAlchemyError):
        logger.exception("Could not persist completed match for room %s", room_id)
        return None


def list_match_history(
    room_id: int,
    room_uuid: str | None = None,
    limit: int = 50,
) -> list[Match]:
    """Return the newest saved rounds for a room, including after room cleanup."""
    with SessionLocal() as session:
        if room_uuid is None:
            room_uuid = session.scalar(
                select(Match.room_uuid)
                .where(Match.room_id == room_id)
                .order_by(Match.id.desc())
                .limit(1)
            )
        if room_uuid is None:
            return []
        return list(
            session.scalars(
                select(Match)
                .where(Match.room_id == room_id)
                .where(Match.room_uuid == room_uuid)
                .order_by(Match.round_number.desc())
                .limit(limit)
            ).all()
        )


def match_payload(match: Match) -> dict[str, Any]:
    """Serialize a persisted match without relying on an open DB session."""
    return {
        "id": match.id,
        "room_id": match.room_id,
        "room_uuid": match.room_uuid,
        "round_number": match.round_number,
        "room_name": match.room_name,
        "red_player": match.red_player,
        "black_player": match.black_player,
        "result": match.result,
        "reason": match.reason,
        "winner": match.winner,
        "notation": match.notation,
        "final_fen": match.final_fen,
        "finished_at": match.finished_at,
    }
