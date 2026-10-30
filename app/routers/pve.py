"""PvE game setup, AI move, and existing-WebSocket event endpoints."""

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from ..ai_engine import DIFFICULTY_SETTINGS, apply_ai_move, get_best_move
from ..pve_schemas import (
    PveAiMoveRequest,
    PveAiMoveResponse,
    PveDifficultyOption,
    PveGameStartRequest,
    PveGameStartResponse,
    PveMoveResponse,
    PveOptionsResponse,
    PveSocketMoveRequest,
)
from ..xiangqi import (
    GameStatus,
    Side,
    XiangqiState,
    apply_move,
    game_status,
    legal_moves,
)


router = APIRouter()
logger = logging.getLogger(__name__)


@dataclass
class _PveSocketGame:
    player_side: Side
    last_ai_state: XiangqiState | None = None
    pending_fen: str | None = None
    generation: int = 0


def _is_one_player_move(
    previous_ai_state: XiangqiState,
    submitted_state: XiangqiState,
    player_side: Side,
) -> bool:
    """Check the next FEN is exactly one legal player move after the AI move."""
    if previous_ai_state.turn is not player_side or submitted_state.turn is not player_side.opponent:
        return False
    return any(
        apply_move(previous_ai_state, move).to_fen() == submitted_state.to_fen()
        for move in legal_moves(previous_ai_state)
    )


def _socket_error(
    reason: str,
    *,
    game_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {"reason": reason}
    if game_id is not None:
        data["game_id"] = game_id
    if request_id is not None:
        data["request_id"] = request_id
    return {"event": "pve:error", "data": data}


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

    result = get_best_move(
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


@router.websocket("/ws")
async def pve_socket(websocket: WebSocket) -> None:
    """Handle PvE event envelopes over the project's FastAPI WebSocket transport.

    The repository has no Socket.IO server/dependency. Messages therefore use
    ``{"event": "pve:request_move", "data": {...}}`` over the existing
    WebSocket stack; response envelopes keep the requested event names.
    """
    await websocket.accept()
    games: OrderedDict[str, _PveSocketGame] = OrderedDict()
    seen_requests: OrderedDict[tuple[str, str], None] = OrderedDict()
    search_tasks: set[asyncio.Task[None]] = set()
    send_lock = asyncio.Lock()

    async def send_event(event: str, data: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_json({"event": event, "data": data})

    async def send_error(
        reason: str,
        *,
        game_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        event = _socket_error(reason, game_id=game_id, request_id=request_id)
        await send_event(event["event"], event["data"])

    async def search_and_send(
        payload: PveSocketMoveRequest,
        state: XiangqiState,
        game: _PveSocketGame,
        generation: int,
    ) -> None:
        try:
            result = await run_in_threadpool(
                get_best_move,
                state,
                payload.difficulty,
                depth=payload.selected_depth,
            )
            if not _request_is_current(game, generation, payload.fen):
                return
            if result is None:
                game.pending_fen = None
                await send_error(
                    "game_over",
                    game_id=payload.game_id,
                    request_id=payload.request_id,
                )
                return

            next_state = apply_ai_move(state, result)
            response_data = {
                "game_id": payload.game_id,
                "request_id": payload.request_id,
                "best_move": {
                    "from": list(result.move.origin),
                    "to": list(result.move.destination),
                },
                "difficulty": payload.difficulty.value,
                "search_depth": result.depth,
                "fen": next_state.to_fen(),
                "score": result.score,
                "nodes": result.nodes,
                "cutoffs": result.cutoffs,
            }
            async with send_lock:
                if not _request_is_current(game, generation, payload.fen):
                    return
                game.last_ai_state = next_state
                game.pending_fen = None
                await websocket.send_json(
                    {"event": "pve:best_move", "data": response_data}
                )
        except asyncio.CancelledError:
            raise
        except (WebSocketDisconnect, RuntimeError):
            return
        except Exception:
            logger.exception("PvE socket search failed for game %s", payload.game_id)
            if _request_is_current(game, generation, payload.fen):
                game.pending_fen = None
                await send_error(
                    "search_failed",
                    game_id=payload.game_id,
                    request_id=payload.request_id,
                )

    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await send_error("invalid_payload")
                continue

            event_name = message.get("event", message.get("type"))
            if event_name != "pve:request_move":
                await send_error("unsupported_event")
                continue

            raw_data = message.get("data")
            if raw_data is None:
                raw_data = {
                    key: value
                    for key, value in message.items()
                    if key not in {"event", "type"}
                }
            if not isinstance(raw_data, dict):
                await send_error("invalid_payload")
                continue

            try:
                payload = PveSocketMoveRequest.model_validate(raw_data)
                state = XiangqiState.from_fen(payload.fen)
            except (ValidationError, ValueError):
                await send_error(
                    "invalid_game_state",
                    game_id=raw_data.get("game_id") if isinstance(raw_data.get("game_id"), str) else None,
                    request_id=raw_data.get("request_id") if isinstance(raw_data.get("request_id"), str) else None,
                )
                continue

            request_key = (payload.game_id, payload.request_id)
            if request_key in seen_requests:
                await send_error(
                    "duplicate_request",
                    game_id=payload.game_id,
                    request_id=payload.request_id,
                )
                continue
            seen_requests[request_key] = None
            if len(seen_requests) > 1024:
                seen_requests.popitem(last=False)

            current_status = game_status(state)
            if current_status not in {GameStatus.ACTIVE, GameStatus.CHECK}:
                await send_error(
                    "game_over",
                    game_id=payload.game_id,
                    request_id=payload.request_id,
                )
                continue
            if state.turn is payload.player_side:
                await send_error(
                    "not_ai_turn",
                    game_id=payload.game_id,
                    request_id=payload.request_id,
                )
                continue

            game = games.get(payload.game_id)
            if game is None:
                game = _PveSocketGame(player_side=payload.player_side)
                games[payload.game_id] = game
                if len(games) > 100:
                    for oldest_game_id, oldest_game in games.items():
                        if oldest_game_id != payload.game_id and oldest_game.pending_fen is None:
                            games.pop(oldest_game_id)
                            break
            elif game.player_side is not payload.player_side:
                await send_error(
                    "player_side_changed",
                    game_id=payload.game_id,
                    request_id=payload.request_id,
                )
                continue
            else:
                games.move_to_end(payload.game_id)
                if game.pending_fen is not None:
                    if game.pending_fen == payload.fen:
                        await send_error(
                            "duplicate_position",
                            game_id=payload.game_id,
                            request_id=payload.request_id,
                        )
                        continue
                    if game.last_ai_state is not None and not _is_one_player_move(
                        game.last_ai_state,
                        state,
                        payload.player_side,
                    ):
                        await send_error(
                            "stale_or_invalid_board",
                            game_id=payload.game_id,
                            request_id=payload.request_id,
                        )
                        continue
                    # A newer valid FEN supersedes work still in progress; the
                    # old generation is discarded when its search completes.
                elif game.last_ai_state is not None and not _is_one_player_move(
                    game.last_ai_state,
                    state,
                    payload.player_side,
                ):
                    await send_error(
                        "stale_or_invalid_board",
                        game_id=payload.game_id,
                        request_id=payload.request_id,
                    )
                    continue

            game.generation += 1
            generation = game.generation
            game.pending_fen = payload.fen
            await send_event(
                "pve:thinking",
                {
                    "game_id": payload.game_id,
                    "request_id": payload.request_id,
                    "difficulty": payload.difficulty.value,
                    "search_depth": payload.selected_depth,
                },
            )
            task = asyncio.create_task(
                search_and_send(payload, state, game, generation),
                name=f"pve-search-{payload.game_id}-{payload.request_id}",
            )
            search_tasks.add(task)
            task.add_done_callback(search_tasks.discard)
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        logger.debug("PvE WebSocket closed while sending an event")
    finally:
        for task in tuple(search_tasks):
            task.cancel()
        if search_tasks:
            await asyncio.gather(*search_tasks, return_exceptions=True)


def _request_is_current(
    game: _PveSocketGame,
    generation: int,
    fen: str,
) -> bool:
    return game.generation == generation and game.pending_fen == fen
