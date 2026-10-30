"""Difficulty presets and alpha-beta search for Xiangqi positions."""

from __future__ import annotations

import random
import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from threading import Lock

from .xiangqi import (
    Board,
    GameStatus,
    Move,
    Piece,
    PieceKind,
    Side,
    XiangqiState,
    apply_move,
    game_status,
    game_winner,
    is_in_check,
    legal_moves,
)


MATE_SCORE = 1_000_000
_INFINITY = MATE_SCORE * 2
_PIECE_VALUES = {
    PieceKind.GENERAL: 10_000,
    PieceKind.ROOK: 900,
    PieceKind.CANNON: 450,
    PieceKind.HORSE: 400,
    PieceKind.ADVISOR: 200,
    PieceKind.ELEPHANT: 200,
    PieceKind.PAWN: 100,
}
_MAX_CACHED_POSITIONS = 20_000
_HARD_NODE_LIMIT = 1_000_000
_HARD_DEPTH_FIVE_BUDGET_SECONDS = 1.5
_MOVE_CACHE: OrderedDict[str, tuple[Move, ...]] = OrderedDict()
_MOVE_CACHE_LOCK = Lock()


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


_MAX_QUIET_MOVES = {
    Difficulty.MEDIUM: 10,
    Difficulty.HARD: 5,
}


@dataclass(frozen=True)
class DifficultySettings:
    min_depth: int
    max_depth: int
    default_depth: int
    random_move_probability: float


DIFFICULTY_SETTINGS = {
    Difficulty.EASY: DifficultySettings(
        min_depth=1,
        max_depth=1,
        default_depth=1,
        random_move_probability=0.30,
    ),
    Difficulty.MEDIUM: DifficultySettings(
        min_depth=3,
        max_depth=3,
        default_depth=3,
        random_move_probability=0.0,
    ),
    Difficulty.HARD: DifficultySettings(
        min_depth=4,
        max_depth=5,
        default_depth=5,
        random_move_probability=0.0,
    ),
}


@dataclass(frozen=True)
class SearchResult:
    move: Move
    score: int
    depth: int
    nodes: int
    cutoffs: int


@dataclass(frozen=True)
class _TranspositionEntry:
    depth: int
    score: int
    bound: str
    best_move: Move | None


@dataclass
class _SearchContext:
    table: dict[str, _TranspositionEntry]
    killers: dict[int, tuple[Move, ...]]
    node_limit: int | None = None
    deadline: float | None = None
    nodes: int = 0
    cutoffs: int = 0
    repetition_hits: int = 0


def difficulty_settings(difficulty: Difficulty | str) -> DifficultySettings:
    """Return supported depth and randomness settings for a difficulty level."""
    return DIFFICULTY_SETTINGS[Difficulty(difficulty)]


def _legal_moves_for_position(state: XiangqiState) -> tuple[Move, ...]:
    """Cache move generation by board geometry, independent of game history."""
    position_key = state.position_key
    with _MOVE_CACHE_LOCK:
        cached_moves = _MOVE_CACHE.get(position_key)
        if cached_moves is not None:
            _MOVE_CACHE.move_to_end(position_key)
            return cached_moves

    moves = tuple(legal_moves(state))
    with _MOVE_CACHE_LOCK:
        _MOVE_CACHE[position_key] = moves
        if len(_MOVE_CACHE) > _MAX_CACHED_POSITIONS:
            _MOVE_CACHE.popitem(last=False)
    return moves


def _piece_at(state: XiangqiState, square: tuple[int, int]) -> Piece | None:
    return state.board[square[0]][square[1]]


def _search_child(state: XiangqiState, move: Move) -> XiangqiState:
    origin_row, origin_column = move.origin
    target_row, target_column = move.destination
    moving_piece = state.board[origin_row][origin_column]
    if moving_piece is None:
        raise ValueError("The origin square is empty")
    captured_piece = state.board[target_row][target_column]

    rows = [list(row) for row in state.board]
    rows[origin_row][origin_column] = None
    rows[target_row][target_column] = moving_piece
    return XiangqiState(
        board=tuple(tuple(row) for row in rows),
        turn=state.turn.opponent,
        halfmove_clock=(
            0
            if captured_piece is not None or moving_piece.kind is PieceKind.PAWN
            else state.halfmove_clock + 1
        ),
        fullmove_number=state.fullmove_number + (state.turn is Side.BLACK),
    )


def _only_generals_remain(state: XiangqiState) -> bool:
    return all(
        piece is None or piece.kind is PieceKind.GENERAL
        for row in state.board
        for piece in row
    )


def _evaluate(state: XiangqiState, difficulty: Difficulty) -> int:
    """Evaluate a position from Red's perspective."""
    red_score = 0

    for row_index, row in enumerate(state.board):
        for column_index, piece in enumerate(row):
            if piece is None:
                continue
            sign = 1 if piece.side is Side.RED else -1
            value = _PIECE_VALUES[piece.kind]

            if piece.kind is PieceKind.PAWN:
                progress = (
                    max(0, 6 - row_index)
                    if piece.side is Side.RED
                    else max(0, row_index - 3)
                )
                value += progress * (2 if difficulty is Difficulty.EASY else 8)
                crossed_river = (
                    row_index <= 4
                    if piece.side is Side.RED
                    else row_index >= 5
                )
                if crossed_river:
                    value += 12 if difficulty is Difficulty.EASY else 20

            centrality = 4 - abs(column_index - 4)
            activity_weight = {
                PieceKind.ROOK: 4,
                PieceKind.CANNON: 5,
                PieceKind.HORSE: 5,
                PieceKind.PAWN: 2,
                PieceKind.ADVISOR: 1,
                PieceKind.ELEPHANT: 1,
                PieceKind.GENERAL: 0,
            }[piece.kind]
            value += centrality * activity_weight

            if difficulty is Difficulty.HARD:
                if (
                    piece.kind in {PieceKind.ROOK, PieceKind.CANNON, PieceKind.HORSE}
                    and 3 <= row_index <= 6
                    and 3 <= column_index <= 5
                ):
                    value += 18
                if piece.kind is PieceKind.PAWN and 3 <= column_index <= 5:
                    value += 6

            red_score += sign * value

    if difficulty is Difficulty.HARD:
        if is_in_check(state, Side.RED):
            red_score -= 60
        if is_in_check(state, Side.BLACK):
            red_score += 60

    return red_score


def evaluate_board(
    board: XiangqiState | Board,
    ai_side: Side | str,
) -> int:
    """Evaluate a Xiangqi position from the requested side's perspective.

    ``board`` normally is the rules engine's immutable ``XiangqiState``. A raw
    board tuple is also accepted for callers that already use that structure;
    in that case the active side defaults to Red because a board alone has no
    turn information.
    """
    state = board if isinstance(board, XiangqiState) else XiangqiState(board=board)
    side = Side(ai_side)
    status = game_status(state)
    if status is GameStatus.DRAW:
        return 0
    if status not in {GameStatus.ACTIVE, GameStatus.CHECK}:
        winner = state.turn.opponent if status in {GameStatus.CHECKMATE, GameStatus.STALEMATE} else None
        if winner is None:
            winner = game_winner(state)
        if winner is None:
            return 0
        return MATE_SCORE if winner is side else -MATE_SCORE

    red_score = _evaluate(state, Difficulty.MEDIUM)
    return red_score if side is Side.RED else -red_score


def _move_order_score(
    state: XiangqiState,
    move: Move,
    *,
    preferred_move: Move | None,
    killer_moves: tuple[Move, ...],
    difficulty: Difficulty,
) -> int:
    if move == preferred_move:
        return 2_000_000

    attacker = _piece_at(state, move.origin)
    target = _piece_at(state, move.destination)
    if attacker is None:
        return -_INFINITY

    if target is not None:
        score = 1_000_000 + 16 * _PIECE_VALUES[target.kind] - _PIECE_VALUES[attacker.kind]
    elif move in killer_moves:
        return 100_000 - killer_moves.index(move) * 100
    else:
        destination_row, destination_column = move.destination
        center_score = 4 - abs(destination_column - 4)
        score = center_score * (2 if difficulty is Difficulty.HARD else 1)
        if attacker.kind is PieceKind.PAWN:
            advance = (
                move.origin[0] - destination_row
                if attacker.side is Side.RED
                else destination_row - move.origin[0]
            )
            score += advance * 2

    if difficulty is Difficulty.HARD and is_in_check(_search_child(state, move)):
        score += 500_000
    return score


def _ordered_moves(
    state: XiangqiState,
    moves: tuple[Move, ...],
    *,
    preferred_move: Move | None,
    killer_moves: tuple[Move, ...],
    difficulty: Difficulty,
) -> list[Move]:
    return sorted(
        moves,
        key=lambda move: (
            -_move_order_score(
                state,
                move,
                preferred_move=preferred_move,
                killer_moves=killer_moves,
                difficulty=difficulty,
            ),
            move.origin,
            move.destination,
        ),
    )


def choose_move(
    state: XiangqiState,
    difficulty: Difficulty | str = Difficulty.MEDIUM,
    *,
    depth: int | None = None,
    rng: random.Random | random.SystemRandom | None = None,
) -> SearchResult | None:
    """Choose a legal move using difficulty-configured minimax and alpha-beta.

    Search snapshots retain the board and move counters but omit tournament
    adjudication history. The caller's real state is used to apply the chosen
    move so its WXF history remains intact. Medium and Hard bound quiet-move
    candidates at deeper nodes while retaining captures, checks, and evasions.
    """
    selected_difficulty = Difficulty(difficulty)
    settings = difficulty_settings(selected_difficulty)
    selected_depth = settings.default_depth if depth is None else depth
    if not settings.min_depth <= selected_depth <= settings.max_depth:
        raise ValueError(
            f"{selected_difficulty.value} depth must be between "
            f"{settings.min_depth} and {settings.max_depth}"
        )

    status = game_status(state)
    if status not in {GameStatus.ACTIVE, GameStatus.CHECK}:
        return None

    root_moves = tuple(legal_moves(state))
    if not root_moves:
        return None

    random_source = rng or random.SystemRandom()
    context = _SearchContext(
        table={},
        killers={},
    )
    path = {state.position_key: 1}
    is_maximizing = state.turn is Side.RED
    best_move = root_moves[0]
    best_score = 0
    completed_depth = 0

    for current_depth in range(1, selected_depth + 1):
        # Hard always completes at least depth four. The node budget applies
        # only to the optional fifth iteration, which can fall back to depth 4.
        context.node_limit = (
            _HARD_NODE_LIMIT
            if selected_difficulty is Difficulty.HARD
            and current_depth > settings.min_depth
            else None
        )
        context.deadline = (
            time.monotonic() + _HARD_DEPTH_FIVE_BUDGET_SECONDS
            if selected_difficulty is Difficulty.HARD
            and current_depth > settings.min_depth
            else None
        )
        iteration_score = -_INFINITY if is_maximizing else _INFINITY
        iteration_move = best_move
        alpha = -_INFINITY
        beta = _INFINITY

        try:
            for move in _ordered_moves(
                state,
                root_moves,
                preferred_move=best_move,
                killer_moves=(),
                difficulty=selected_difficulty,
            ):
                child = _search_child(state, move)
                score = _alpha_beta(
                    child,
                    current_depth - 1,
                    alpha,
                    beta,
                    ply=1,
                    path=path,
                    context=context,
                    difficulty=selected_difficulty,
                )
                if (is_maximizing and score > iteration_score) or (
                    not is_maximizing and score < iteration_score
                ):
                    iteration_score = score
                    iteration_move = move

                if is_maximizing:
                    alpha = max(alpha, iteration_score)
                else:
                    beta = min(beta, iteration_score)
        except _SearchBudgetExceeded:
            break

        best_score = iteration_score
        best_move = iteration_move
        completed_depth = current_depth
        context.table[state.position_key] = _TranspositionEntry(
            depth=current_depth,
            score=best_score,
            bound="exact",
            best_move=best_move,
        )

    if (
        settings.random_move_probability > 0
        and random_source.random() < settings.random_move_probability
    ):
        best_move = random_source.choice(root_moves)
        best_score = 0

    return SearchResult(
        move=best_move,
        score=best_score if is_maximizing else -best_score,
        depth=completed_depth,
        nodes=context.nodes,
        cutoffs=context.cutoffs,
    )


class _SearchBudgetExceeded(Exception):
    """Abort an incomplete iterative-deepening layer at the node budget."""


def minimax(
    state: XiangqiState,
    depth: int,
    alpha: int = -_INFINITY,
    beta: int = _INFINITY,
    ai_side: Side | str = Side.RED,
    *,
    difficulty: Difficulty | str = Difficulty.MEDIUM,
) -> int:
    """Return an alpha-beta minimax score from ``ai_side``'s perspective."""
    if depth < 0:
        raise ValueError("Search depth cannot be negative")
    side = Side(ai_side)
    selected_difficulty = Difficulty(difficulty)
    context = _SearchContext(table={}, killers={})
    path = {state.position_key: 1}
    if side is Side.RED:
        return _alpha_beta(
            state,
            depth,
            alpha,
            beta,
            ply=0,
            path=path,
            context=context,
            difficulty=selected_difficulty,
        )
    return -_alpha_beta(
        state,
        depth,
        -beta,
        -alpha,
        ply=0,
        path=path,
        context=context,
        difficulty=selected_difficulty,
    )


def get_best_move(
    state: XiangqiState,
    difficulty: Difficulty | str = Difficulty.MEDIUM,
    *,
    depth: int | None = None,
    rng: random.Random | random.SystemRandom | None = None,
) -> SearchResult | None:
    """Public PvE entry point; preserve ``choose_move`` for existing callers."""
    return choose_move(state, difficulty, depth=depth, rng=rng)


def _alpha_beta(
    state: XiangqiState,
    depth: int,
    alpha: int,
    beta: int,
    *,
    ply: int,
    path: dict[str, int],
    context: _SearchContext,
    difficulty: Difficulty,
) -> int:
    context.nodes += 1
    if context.node_limit is not None and context.nodes > context.node_limit:
        raise _SearchBudgetExceeded
    if (
        context.deadline is not None
        and context.nodes % 32 == 0
        and time.monotonic() >= context.deadline
    ):
        raise _SearchBudgetExceeded
    position_key = state.position_key
    path_occurrences = path.get(position_key, 0)
    if path_occurrences >= 2:
        context.repetition_hits += 1
        return 0

    moves = _legal_moves_for_position(state)
    if not moves:
        return -MATE_SCORE + ply if state.turn is Side.RED else MATE_SCORE - ply
    if _only_generals_remain(state):
        return 0
    if depth <= 0:
        return _evaluate(state, difficulty)

    original_alpha = alpha
    original_beta = beta
    entry = context.table.get(position_key)
    preferred_move = None
    if entry is not None:
        preferred_move = entry.best_move
        if entry.depth >= depth:
            if entry.bound == "exact":
                return entry.score
            if entry.bound == "lower":
                alpha = max(alpha, entry.score)
            elif entry.bound == "upper":
                beta = min(beta, entry.score)
            if alpha >= beta:
                return entry.score

    path[position_key] = path_occurrences + 1
    is_maximizing = state.turn is Side.RED
    best_score = -_INFINITY if is_maximizing else _INFINITY
    best_move = None
    killers = context.killers.get(ply, ())
    quiet_move_limit = _MAX_QUIET_MOVES.get(difficulty)
    reduce_quiet_moves = quiet_move_limit is not None and depth >= 2
    node_in_check = is_in_check(state) if reduce_quiet_moves else False
    quiet_moves_searched = 0
    repetition_hits_before_search = context.repetition_hits

    try:
        for move in _ordered_moves(
            state,
            moves,
            preferred_move=preferred_move,
            killer_moves=killers,
            difficulty=difficulty,
        ):
            child = _search_child(state, move)
            if (
                reduce_quiet_moves
                and not node_in_check
                and _piece_at(state, move.destination) is None
            ):
                gives_check = is_in_check(child, child.turn)
                if not gives_check:
                    if (
                        quiet_move_limit is not None
                        and quiet_moves_searched >= quiet_move_limit
                    ):
                        continue
                    quiet_moves_searched += 1

            score = _alpha_beta(
                child,
                depth - 1,
                alpha,
                beta,
                ply=ply + 1,
                path=path,
                context=context,
                difficulty=difficulty,
            )
            if (is_maximizing and score > best_score) or (
                not is_maximizing and score < best_score
            ):
                best_score = score
                best_move = move

            if is_maximizing:
                alpha = max(alpha, best_score)
            else:
                beta = min(beta, best_score)

            if alpha >= beta:
                context.cutoffs += 1
                if _piece_at(state, move.destination) is None:
                    updated_killers = (move,) + tuple(
                        killer for killer in killers if killer != move
                    )
                    context.killers[ply] = updated_killers[:2]
                break
    finally:
        if path_occurrences:
            path[position_key] = path_occurrences
        else:
            del path[position_key]

    if best_score <= original_alpha:
        bound = "upper"
    elif best_score >= original_beta:
        bound = "lower"
    else:
        bound = "exact"

    previous_entry = context.table.get(position_key)
    if (
        context.repetition_hits == repetition_hits_before_search
        and (previous_entry is None or depth >= previous_entry.depth)
    ):
        context.table[position_key] = _TranspositionEntry(
            depth=depth,
            score=best_score,
            bound=bound,
            best_move=best_move,
        )
    return best_score


def apply_ai_move(state: XiangqiState, result: SearchResult) -> XiangqiState:
    """Apply a search result with the rules engine's full game-history logic."""
    return apply_move(state, result.move)
