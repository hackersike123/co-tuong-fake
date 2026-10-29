"""Stateless PvE game setup and AI move endpoints."""

from fastapi import APIRouter, HTTPException, status

from ..ai_engine import DIFFICULTY_SETTINGS, apply_ai_move, choose_move
from ..pve_schemas import (
    PveAiMoveRequest,
    PveAiMoveResponse,
    PveDifficultyOption,
    PveGameStartRequest,
    PveGameStartResponse,
    PveMoveResponse,
    PveOptionsResponse,
)
from ..xiangqi import Side, XiangqiState


router = APIRouter()


@router.get(
    "/options",
    response_model=PveOptionsResponse,
    summary="Get single-player game options",
)
def get_pve_options() -> PveOptionsResponse:
    """Return starting position and supported sides/difficulty depths."""
    difficulties = {
        level: PveDifficultyOption(
            min_depth=settings.min_depth,
            max_depth=settings.max_depth,
            default_depth=settings.default_depth,
            random_move_probability=settings.random_move_probability,
        )
        for level, settings in DIFFICULTY_SETTINGS.items()
    }
    return PveOptionsResponse(difficulties=difficulties)


@router.post(
    "/games",
    response_model=PveGameStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a single-player game",
)
def start_pve_game(payload: PveGameStartRequest) -> PveGameStartResponse:
    """Return a fresh Xiangqi position and the selected player/AI sides.

    Game state is stateless on the server: the client keeps the returned FEN
    and sends the current FEN when requesting an AI move.
    """
    state = XiangqiState.initial()
    return PveGameStartResponse(
        fen=state.to_fen(),
        player_side=payload.player_side,
        ai_side=payload.player_side.opponent,
        side_to_move=state.turn,
        difficulty=payload.difficulty,
        depth=payload.selected_depth,
    )


@router.post(
    "/ai-move",
    response_model=PveAiMoveResponse,
    summary="Choose and apply an AI move",
)
def request_ai_move(payload: PveAiMoveRequest) -> PveAiMoveResponse:
    """Search the current position and return the chosen legal move and FEN."""
    state = XiangqiState.from_fen(payload.fen)
    if state.turn is payload.player_side:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="It is the player's turn",
        )

    result = choose_move(
        state,
        payload.difficulty,
        depth=payload.selected_depth,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The game is already over",
        )

    next_state = apply_ai_move(state, result)
    return PveAiMoveResponse(
        move=PveMoveResponse(
            from_square=result.move.origin,
            to_square=result.move.destination,
        ),
        fen=next_state.to_fen(),
        ai_side=state.turn,
        difficulty=payload.difficulty,
        depth=result.depth,
        score=result.score,
        nodes=result.nodes,
        cutoffs=result.cutoffs,
    )
