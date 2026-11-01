"""Authenticated profiles and community data derived from completed games."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from redis.exceptions import RedisError
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import Match, User
from ..player_schemas import (
    CommunityMatchResponse,
    CommunitySummaryResponse,
    LeaderboardEntry,
    PlayerStatsResponse,
)
from ..room_store import list_public_rooms
from ..schemas import ProfileUpdateRequest, UserResponse
from ..security import decode_access_token

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = Depends(get_session),
) -> User:
    """Resolve a bearer access token to an active account."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = decode_access_token(authorization[7:].strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _user_matches(session: Session, user_id: int) -> list[Match]:
    return list(
        session.scalars(
            select(Match)
            .where(or_(Match.red_user_id == user_id, Match.black_user_id == user_id))
            .order_by(Match.finished_at.desc(), Match.id.desc())
        ).all()
    )


def _result_counts(matches: Sequence[Match], user_id: int) -> tuple[int, int, int]:
    wins = draws = losses = 0
    for match in matches:
        is_red = match.red_user_id == user_id
        if match.winner is None:
            draws += 1
        elif (match.winner == "w") == is_red:
            wins += 1
        else:
            losses += 1
    return wins, draws, losses


def _win_rate(wins: int, games_played: int) -> float:
    return round(wins * 100 / games_played, 1) if games_played else 0.0


def _leaderboard(session: Session) -> list[LeaderboardEntry]:
    entries: list[LeaderboardEntry] = []
    users = session.scalars(
        select(User).where(User.is_active.is_(True)).order_by(User.elo.desc(), User.id.asc())
    ).all()
    for user in users:
        matches = _user_matches(session, user.id)
        if not matches:
            continue
        wins, draws, losses = _result_counts(matches, user.id)
        entries.append(
            LeaderboardEntry(
                rank=0,
                user_id=user.id,
                username=user.username,
                display_name=user.display_name,
                elo=user.elo,
                games_played=len(matches),
                wins=wins,
                draws=draws,
                losses=losses,
                win_rate=_win_rate(wins, len(matches)),
            )
        )
    entries.sort(key=lambda row: (-row.elo, -row.wins, row.display_name.casefold(), row.user_id))
    return [entry.model_copy(update={"rank": rank}) for rank, entry in enumerate(entries, start=1)]


@router.get("/users/me", response_model=UserResponse, summary="Get the signed-in player profile")
def read_current_user(user: CurrentUser) -> User:
    return user


@router.patch("/users/me", response_model=UserResponse, summary="Update the signed-in display name")
def update_current_user(
    payload: ProfileUpdateRequest,
    user: CurrentUser,
    session: SessionDep,
) -> User:
    user.display_name = payload.display_name
    try:
        session.commit()
        session.refresh(user)
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail="Profile service is temporarily unavailable") from exc
    return user


@router.get("/users/me/stats", response_model=PlayerStatsResponse, summary="Get saved player statistics")
def current_user_stats(user: CurrentUser, session: SessionDep) -> PlayerStatsResponse:
    matches = _user_matches(session, user.id)
    wins, draws, losses = _result_counts(matches, user.id)
    rank_by_user = {entry.user_id: entry.rank for entry in _leaderboard(session)}
    return PlayerStatsResponse(
        user_id=user.id,
        display_name=user.display_name,
        username=user.username,
        elo=user.elo,
        games_played=len(matches),
        wins=wins,
        draws=draws,
        losses=losses,
        win_rate=_win_rate(wins, len(matches)),
        rank=rank_by_user.get(user.id),
    )


@router.get("/users/me/matches", response_model=list[CommunityMatchResponse], summary="Get saved games for the signed-in player")
def current_user_matches(user: CurrentUser, session: SessionDep) -> list[Match]:
    return _user_matches(session, user.id)


@router.get("/community/leaderboard", response_model=list[LeaderboardEntry], summary="List players with recorded games")
def community_leaderboard(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[LeaderboardEntry]:
    return _leaderboard(session)[:limit]


@router.get("/community/recent-matches", response_model=list[CommunityMatchResponse], summary="List recent public completed games")
def recent_public_matches(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Match]:
    return list(
        session.scalars(
            select(Match)
            .where(Match.is_public.is_(True))
            .where(Match.has_password.is_(False))
            .where(Match.allow_spectators.is_(True))
            .order_by(Match.finished_at.desc(), Match.id.desc())
            .limit(limit)
        ).all()
    )


@router.get("/community/summary", response_model=CommunitySummaryResponse, summary="Get live community counts")
def community_summary(session: SessionDep) -> CommunitySummaryResponse:
    try:
        open_rooms = len(list_public_rooms())
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Room service is temporarily unavailable") from exc
    registered_players = len(
        session.scalars(select(User.id).where(User.is_active.is_(True))).all()
    )
    completed_public_games = len(
        session.scalars(select(Match.id).where(Match.is_public.is_(True))).all()
    )
    return CommunitySummaryResponse(
        registered_players=registered_players,
        open_public_rooms=open_rooms,
        completed_public_games=completed_public_games,
    )
