"""Tests for the Xiangqi PvE search engine and API."""

import random
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import ai_engine
from app.ai_engine import (
    MATE_SCORE,
    Difficulty,
    _evaluate,
    choose_move,
    difficulty_settings,
    evaluate_board,
    get_best_move,
    minimax,
)
from app.routers import pve as pve_routes
from app.routers.pve import router as pve_router
from app.xiangqi import Move, Side, XiangqiState, apply_move, legal_moves


SMALL_POSITION_FEN = "3k5/9/9/9/9/R8/9/9/9/5K3 w - - 0 1"


@pytest.fixture
def api_client() -> TestClient:
    app = FastAPI()
    app.include_router(pve_router, prefix="/api/v1/pve")
    return TestClient(app)


def _receive_pve_event(websocket, event_name: str) -> dict:
    for _ in range(10):
        event = websocket.receive_json()
        if event.get("event") == event_name:
            return event["data"]
    raise AssertionError(f"Did not receive PvE event {event_name!r}")


def test_difficulty_profiles_match_supported_depths() -> None:
    easy = difficulty_settings(Difficulty.EASY)
    medium = difficulty_settings(Difficulty.MEDIUM)
    hard = difficulty_settings(Difficulty.HARD)

    assert (easy.min_depth, easy.max_depth, easy.default_depth) == (1, 1, 1)
    assert easy.random_move_probability == 0.30
    assert (medium.min_depth, medium.max_depth, medium.default_depth) == (3, 3, 3)
    assert medium.random_move_probability == 0
    assert (hard.min_depth, hard.max_depth, hard.default_depth) == (4, 5, 5)
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
    assert result.nodes > 0
    assert result.move in legal_moves(state)


def test_easy_randomizes_only_after_search_at_the_configured_probability() -> None:
    class FixedRandom:
        def __init__(self, value: float) -> None:
            self.value = value
            self.choice_called = False

        def random(self) -> float:
            return self.value

        def choice(self, moves):
            self.choice_called = True
            return moves[-1]

    state = XiangqiState.initial()
    best_rng = FixedRandom(0.99)
    random_rng = FixedRandom(0.0)
    best_result = choose_move(state, Difficulty.EASY, rng=best_rng)
    random_result = choose_move(state, Difficulty.EASY, rng=random_rng)

    assert best_result is not None and random_result is not None
    assert best_rng.choice_called is False
    assert random_rng.choice_called is True
    assert best_result.nodes > 0 and random_result.nodes > 0
    assert random_result.move == legal_moves(state)[-1]


@pytest.mark.parametrize(
    ("difficulty", "depth"),
    [(Difficulty.MEDIUM, 3), (Difficulty.HARD, 4), (Difficulty.HARD, 5)],
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


def test_hard_search_falls_back_to_completed_depth_four(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ai_engine, "_HARD_NODE_LIMIT", 1)
    state = XiangqiState.from_fen(SMALL_POSITION_FEN)

    result = get_best_move(state, Difficulty.HARD, depth=5)

    assert result is not None
    assert result.depth == 4
    assert result.move in legal_moves(state)


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
        (Difficulty.EASY, 2),
        (Difficulty.MEDIUM, 2),
        (Difficulty.MEDIUM, 4),
        (Difficulty.HARD, 3),
        (Difficulty.HARD, 6),
    ],
)
def test_depth_outside_selected_difficulty_is_rejected(
    difficulty: Difficulty,
    depth: int,
) -> None:
    with pytest.raises(ValueError, match="depth must be between"):
        choose_move(XiangqiState.initial(), difficulty, depth=depth)


def test_evaluate_board_uses_ai_perspective_and_requested_piece_values() -> None:
    red_horse = XiangqiState.from_fen("3k5/9/9/9/9/H8/9/9/9/5K3 w - - 0 1")

    assert evaluate_board(red_horse, Side.RED) == 400
    assert evaluate_board(red_horse, Side.BLACK) == -400


def test_evaluate_board_rewards_pawns_after_crossing_river() -> None:
    red_before = XiangqiState.from_fen("3k5/9/9/9/9/P8/9/9/9/5K3 w - - 0 1")
    red_after = XiangqiState.from_fen("3k5/9/9/9/P8/9/9/9/9/5K3 w - - 0 1")
    black_before = XiangqiState.from_fen("3k5/9/9/9/p8/9/9/9/9/5K3 w - - 0 1")
    black_after = XiangqiState.from_fen("3k5/9/9/9/9/p8/9/9/9/5K3 w - - 0 1")

    assert evaluate_board(red_after, Side.RED) > evaluate_board(red_before, Side.RED)
    assert evaluate_board(black_after, Side.BLACK) > evaluate_board(black_before, Side.BLACK)


def test_terminal_evaluation_and_minimax_are_side_aware() -> None:
    black_is_checkmated = XiangqiState.from_fen(
        "3Rk1R2/9/4R4/9/9/9/9/9/9/3K5 b - - 0 1"
    )

    assert evaluate_board(black_is_checkmated, Side.RED) == MATE_SCORE
    assert evaluate_board(black_is_checkmated, Side.BLACK) == -MATE_SCORE
    assert minimax(black_is_checkmated, 2, ai_side=Side.RED) == MATE_SCORE
    assert minimax(black_is_checkmated, 2, ai_side=Side.BLACK) == -MATE_SCORE


def test_search_does_not_mutate_the_original_xiangqi_state() -> None:
    state = XiangqiState.initial()
    original_fen = state.to_fen()
    original_board = state.board

    result = get_best_move(state, Difficulty.MEDIUM)

    assert result is not None
    assert result.move in legal_moves(state)
    assert state.to_fen() == original_fen
    assert state.board == original_board


def test_options_endpoint_lists_side_and_depth_choices(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/pve/options")

    assert response.status_code == 200
    options = response.json()
    assert options["sides"] == ["w", "b"]
    assert options["difficulties"]["easy"]["min_depth"] == 1
    assert options["difficulties"]["easy"]["max_depth"] == 1
    assert options["difficulties"]["medium"]["min_depth"] == 3
    assert options["difficulties"]["medium"]["max_depth"] == 3
    assert options["difficulties"]["hard"]["min_depth"] == 4
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


def test_pve_websocket_thinks_and_returns_a_legal_move(api_client: TestClient) -> None:
    state = XiangqiState.initial()
    with api_client.websocket_connect("/api/v1/pve/ws") as websocket:
        websocket.send_json(
            {
                "event": "pve:request_move",
                "data": {
                    "game_id": "pve_001",
                    "request_id": "req_001",
                    "fen": state.to_fen(),
                    "player_side": "b",
                    "difficulty": "easy",
                },
            }
        )
        thinking = _receive_pve_event(websocket, "pve:thinking")
        result = _receive_pve_event(websocket, "pve:best_move")

    assert thinking == {
        "game_id": "pve_001",
        "request_id": "req_001",
        "difficulty": "easy",
        "search_depth": 1,
    }
    move = Move(tuple(result["best_move"]["from"]), tuple(result["best_move"]["to"]))
    assert move in legal_moves(state)
    assert result["game_id"] == "pve_001"
    assert result["request_id"] == "req_001"
    assert result["search_depth"] == 1
    assert result["fen"] == apply_move(state, move).to_fen()


def test_pve_websocket_rejects_wrong_turn_and_invalid_fen(
    api_client: TestClient,
) -> None:
    with api_client.websocket_connect("/api/v1/pve/ws") as websocket:
        websocket.send_json(
            {
                "event": "pve:request_move",
                "data": {
                    "game_id": "wrong_turn",
                    "request_id": "req_1",
                    "fen": XiangqiState.initial().to_fen(),
                    "player_side": "w",
                    "difficulty": "easy",
                },
            }
        )
        wrong_turn = _receive_pve_event(websocket, "pve:error")
        websocket.send_json(
            {
                "event": "pve:request_move",
                "data": {
                    "game_id": "bad_fen",
                    "request_id": "req_2",
                    "fen": "not-a-fen",
                    "player_side": "b",
                },
            }
        )
        invalid_fen = _receive_pve_event(websocket, "pve:error")

    assert wrong_turn["reason"] == "not_ai_turn"
    assert invalid_fen["reason"] == "invalid_game_state"


def test_pve_websocket_deduplicates_request_ids(api_client: TestClient) -> None:
    payload = {
        "event": "pve:request_move",
        "data": {
            "game_id": "duplicate_game",
            "request_id": "duplicate_id",
            "fen": XiangqiState.initial().to_fen(),
            "player_side": "b",
            "difficulty": "easy",
        },
    }
    with api_client.websocket_connect("/api/v1/pve/ws") as websocket:
        websocket.send_json(payload)
        websocket.send_json(payload)
        received: list[dict] = []
        while not any(
            event["event"] == "pve:error"
            and event["data"]["reason"] == "duplicate_request"
            for event in received
        ):
            received.append(websocket.receive_json())

    assert any(event["event"] == "pve:thinking" for event in received)
    assert sum(event["event"] == "pve:best_move" for event in received) <= 1


def test_pve_websocket_discards_a_superseded_search(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_state = XiangqiState.initial()
    second_state = XiangqiState.from_fen(SMALL_POSITION_FEN)
    real_get_best_move = pve_routes.get_best_move
    first_started = threading.Event()
    release_first = threading.Event()
    first_finished = threading.Event()
    stale_checked = threading.Event()
    original_is_current = pve_routes._request_is_current

    def delayed_search(state, difficulty, *, depth=None):
        if state.to_fen() == first_state.to_fen():
            first_started.set()
            release_first.wait(timeout=5)
            try:
                return real_get_best_move(
                    state,
                    difficulty,
                    depth=depth,
                    rng=random.Random(0),
                )
            finally:
                first_finished.set()
        return real_get_best_move(
            state,
            difficulty,
            depth=depth,
            rng=random.Random(0),
        )

    def observe_current(game, generation, fen):
        current = original_is_current(game, generation, fen)
        if fen == first_state.to_fen() and not current:
            stale_checked.set()
        return current

    monkeypatch.setattr(pve_routes, "get_best_move", delayed_search)
    monkeypatch.setattr(pve_routes, "_request_is_current", observe_current)

    try:
        with api_client.websocket_connect("/api/v1/pve/ws") as websocket:
            websocket.send_json(
                {
                    "event": "pve:request_move",
                    "data": {
                        "game_id": "stale_game",
                        "request_id": "old_request",
                        "fen": first_state.to_fen(),
                        "player_side": "b",
                        "difficulty": "easy",
                    },
                }
            )
            assert _receive_pve_event(websocket, "pve:thinking")["request_id"] == "old_request"
            assert first_started.wait(timeout=2)

            websocket.send_json(
                {
                    "event": "pve:request_move",
                    "data": {
                        "game_id": "stale_game",
                        "request_id": "new_request",
                        "fen": second_state.to_fen(),
                        "player_side": "b",
                        "difficulty": "easy",
                    },
                }
            )
            assert _receive_pve_event(websocket, "pve:thinking")["request_id"] == "new_request"
            assert _receive_pve_event(websocket, "pve:best_move")["request_id"] == "new_request"

            release_first.set()
            assert first_finished.wait(timeout=2)
            assert stale_checked.wait(timeout=2)
            websocket.send_json({"event": "unknown:event", "data": {}})
            received: list[dict] = []
            while not any(
                event["event"] == "pve:error"
                and event["data"]["reason"] == "unsupported_event"
                for event in received
            ):
                received.append(websocket.receive_json())
    finally:
        release_first.set()

    assert not any(
        event["event"] == "pve:best_move"
        and event["data"].get("request_id") == "old_request"
        for event in received
    )
