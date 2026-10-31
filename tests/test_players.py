from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, security
from app.database import Base, get_session
from app.models import Match, User
from app.routers.players import router as players_router


@pytest.fixture
def players_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, str, User, User]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", test_sessions)
    monkeypatch.setattr(
        security,
        "JWT_SECRET",
        "player-api-test-secret-that-is-at-least-32-characters-long",
    )

    with test_sessions() as session:
        red = User(
            email="red@example.com",
            username="red",
            display_name="Red Player",
            password_hash="unused",
            is_active=True,
            elo=1016,
        )
        black = User(
            email="black@example.com",
            username="black",
            display_name="Black Player",
            password_hash="unused",
            is_active=True,
            elo=984,
        )
        session.add_all([red, black])
        session.flush()
        session.add_all(
            [
                Match(
                    match_key="public-1",
                    room_id=1,
                    room_uuid="public-room-uuid",
                    round_number=1,
                    room_name="Public game",
                    red_player=red.display_name,
                    black_player=black.display_name,
                    red_user_id=red.id,
                    black_user_id=black.id,
                    result="checkmate",
                    reason="checkmate",
                    winner="w",
                    notation="1. b9-a7",
                    final_fen="test-fen",
                    is_public=True,
                    red_elo_change=16,
                    black_elo_change=-16,
                ),
                Match(
                    match_key="private-1",
                    room_id=2,
                    room_uuid="private-room-uuid",
                    round_number=1,
                    room_name="Private game",
                    red_player=red.display_name,
                    black_player=black.display_name,
                    red_user_id=red.id,
                    black_user_id=black.id,
                    result="agreement",
                    reason="draw_agreement",
                    winner=None,
                    notation="1. b9-a7",
                    final_fen="test-fen",
                    is_public=False,
                    red_elo_change=0,
                    black_elo_change=0,
                    finished_at=datetime.now(timezone.utc),
                ),
            ]
        )
        session.commit()
        red_id, black_id = red.id, black.id

    app = FastAPI()
    app.include_router(players_router, prefix="/api/v1")

    def override_get_session():
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        token, _ = security.create_access_token(red_id, "red@example.com", "red")
        yield client, token, red, black
    app.dependency_overrides.clear()
    engine.dispose()


def test_authenticated_profile_and_stats_use_saved_matches(players_client) -> None:
    client, token, red, _ = players_client
    response = client.get("/api/v1/users/me/stats", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {
        "user_id": red.id,
        "display_name": "Red Player",
        "username": "red",
        "elo": 1016,
        "games_played": 2,
        "wins": 1,
        "draws": 1,
        "losses": 0,
        "win_rate": 50.0,
        "rank": 1,
    }


def test_player_profile_update_is_authenticated_and_persisted(players_client) -> None:
    client, token, _, _ = players_client
    response = client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"display_name": "Red General"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Red General"


def test_leaderboard_and_recent_matches_exclude_private_games(players_client) -> None:
    client, _, red, black = players_client
    leaderboard = client.get("/api/v1/community/leaderboard")
    assert leaderboard.status_code == 200
    assert [row["username"] for row in leaderboard.json()] == ["red", "black"]
    assert leaderboard.json()[0]["games_played"] == 2

    recent = client.get("/api/v1/community/recent-matches")
    assert recent.status_code == 200
    assert [match["match_key"] for match in recent.json()] == ["public-1"]
    assert recent.json()[0]["red_player"] == red.display_name
    assert recent.json()[0]["black_player"] == black.display_name


def test_private_profile_endpoints_reject_missing_or_invalid_tokens(players_client) -> None:
    client, _, _, _ = players_client
    assert client.get("/api/v1/users/me/stats").status_code == 401
    assert client.get(
        "/api/v1/users/me/stats",
        headers={"Authorization": "Bearer invalid-token"},
    ).status_code == 401
