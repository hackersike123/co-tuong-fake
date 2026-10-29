"""Tests for the Xiangqi PvE search engine and API."""

import random

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai_engine import Difficulty, _evaluate, choose_move, difficulty_settings
from app.routers.pve import router as pve_router
from app.xiangqi import Move, Side, XiangqiState, apply_move, legal_moves


SMALL_POSITION_FEN = "3k5/9/9/9/9/R8/9/9/9/5K3 w - - 0 1"


@pytest.fixture
def api_client() -> TestClient:
    app = FastAPI()
    app.include_router(pve_router, prefix="/api/v1/pve")
    return TestClient(app)


def test_difficulty_profiles_match_supported_depths() -> None:
    easy = difficulty_settings(Difficulty.EASY)
    medium = difficulty_settings(Difficulty.MEDIUM)
    hard = difficulty_settings(Difficulty.HARD)

    assert (easy.min_depth, easy.max_depth) == (1, 2)
    assert 0 < easy.random_move_probability < 1
    assert (medium.min_depth, medium.max_depth) == (3, 4)
    assert medium.random_move_probability == 0
    assert (hard.min_depth, hard.max_depth) == (5, 5)
    assert hard.random_move_probability == 0


def test_easy_level_can_select_a_random_legal_move() -> None:
    state = XiangqiState.initial()

    result = choose_move(
        state,
        Difficulty.EASY,
        depth=1,
        rng=random.Random(1),
    )

    assert result is not None
    assert result.depth == 1
    assert result.nodes == 0
    assert result.move in legal_moves(state)


@pytest.mark.parametrize(
    ("difficulty", "depth"),
    [(Difficulty.MEDIUM, 3), (Difficulty.HARD, 5)],
)
def test_alpha_beta_search_returns_legal_move_at_requested_depth(
    difficulty: Difficulty,
    depth: int,
) -> None:
    state = XiangqiState.from_fen(SMALL_POSITION_FEN)

    result = choose_move(state, difficulty, depth=depth, rng=random.Random(0))

    assert result is not None
    assert result.depth == depth
    assert result.move in legal_moves(state)
    assert result.nodes > 0
    assert result.cutoffs > 0


def test_alpha_beta_takes_a_forced_mating_capture() -> None:
    state = XiangqiState.from_fen("3k5/9/9/9/9/R2h5/9/9/9/5K3 w - - 0 1")

    result = choose_move(state, Difficulty.MEDIUM, depth=3)

    assert result is not None
    assert result.move == Move((5, 0), (5, 3))


def test_hard_evaluation_rewards_central_control() -> None:
    center_rook = XiangqiState.from_fen("3k5/9/9/9/9/4R4/9/9/9/5K3 w - - 0 1")
    edge_rook = XiangqiState.from_fen("3k5/9/9/9/9/R8/9/9/9/5K3 w - - 0 1")

    assert _evaluate(center_rook, Difficulty.HARD) > _evaluate(
        edge_rook,
        Difficulty.HARD,
    )


@pytest.mark.parametrize(
    ("difficulty", "depth"),
    [
        (Difficulty.EASY, 3),
        (Difficulty.MEDIUM, 2),
        (Difficulty.HARD, 4),
        (Difficulty.HARD, 6),
    ],
)
def test_depth_outside_selected_difficulty_is_rejected(
    difficulty: Difficulty,
    depth: int,
) -> None:
    with pytest.raises(ValueError, match="depth must be between"):
        choose_move(XiangqiState.initial(), difficulty, depth=depth)


def test_options_endpoint_lists_side_and_depth_choices(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/pve/options")

    assert response.status_code == 200
    options = response.json()
    assert options["sides"] == ["w", "b"]
    assert options["difficulties"]["easy"]["min_depth"] == 1
    assert options["difficulties"]["easy"]["max_depth"] == 2
    assert options["difficulties"]["medium"]["min_depth"] == 3
    assert options["difficulties"]["hard"]["min_depth"] == 5
    assert options["difficulties"]["hard"]["max_depth"] == 5


def test_start_game_returns_initial_position_and_selected_sides(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/v1/pve/games",
        json={"player_side": "b", "difficulty": "hard", "depth": 5},
    )

    assert response.status_code == 201
    assert response.json() == {
        "fen": XiangqiState.initial().to_fen(),
        "player_side": "b",
        "ai_side": "w",
        "side_to_move": "w",
        "difficulty": "hard",
        "depth": 5,
    }


def test_start_game_rejects_depth_outside_difficulty(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/v1/pve/games",
        json={"player_side": "w", "difficulty": "medium", "depth": 2},
    )

    assert response.status_code == 422


def test_ai_move_endpoint_returns_move_and_updated_fen(
    api_client: TestClient,
) -> None:
    state = XiangqiState.initial()
    response = api_client.post(
        "/api/v1/pve/ai-move",
        json={
            "fen": state.to_fen(),
            "player_side": Side.BLACK.value,
            "difficulty": "easy",
            "depth": 1,
        },
    )

    assert response.status_code == 200
    result = response.json()
    move = result["move"]
    from_square = tuple(move["from"])
    to_square = tuple(move["to"])
    assert any(
        legal_move.origin == from_square and legal_move.destination == to_square
        for legal_move in legal_moves(state)
    )
    assert result["ai_side"] == "w"
    assert result["fen"].split()[1] == "b"
    assert result["depth"] == 1


def test_ai_move_endpoint_rejects_a_players_turn(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/pve/ai-move",
        json={
            "fen": XiangqiState.initial().to_fen(),
            "player_side": "w",
            "difficulty": "easy",
            "depth": 1,
        },
    )

    assert response.status_code == 409


def test_ai_move_endpoint_can_play_black_after_the_player_moves_red(
    api_client: TestClient,
) -> None:
    state = apply_move(XiangqiState.initial(), Move((9, 1), (7, 0)))
    response = api_client.post(
        "/api/v1/pve/ai-move",
        json={
            "fen": state.to_fen(),
            "player_side": "w",
            "difficulty": "easy",
            "depth": 1,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["ai_side"] == "b"
    assert result["fen"].split()[1] == "w"


def test_ai_move_endpoint_rejects_invalid_fen(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/pve/ai-move",
        json={"fen": "not-a-fen", "player_side": "b", "difficulty": "easy"},
    )

    assert response.status_code == 422
