"""Xiangqi board state, FEN, move legality, and basic game outcomes.

Squares are ``(row, column)`` pairs. Row 0 is Black's back rank and row 9 is
Red's back rank; columns 0 through 8 run from the a-file to the i-file.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator, TypeAlias


BOARD_ROWS = 10
BOARD_COLUMNS = 9
FEN_FIFTY_MOVE_LIMIT = 100
REPETITION_DRAW_OCCURRENCES = 4

STARTING_FEN = "rheakaehr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RHEAKAEHR w - - 0 1"

Square: TypeAlias = tuple[int, int]


class Side(str, Enum):
    RED = "w"
    BLACK = "b"

    @property
    def opponent(self) -> Side:
        return Side.BLACK if self is Side.RED else Side.RED


class PieceKind(str, Enum):
    GENERAL = "K"
    ADVISOR = "A"
    ELEPHANT = "E"
    ROOK = "R"
    CANNON = "C"
    HORSE = "H"
    PAWN = "P"


class GameStatus(str, Enum):
    ACTIVE = "active"
    CHECK = "check"
    CHECKMATE = "checkmate"
    STALEMATE = "stalemate"
    DRAW = "draw"


@dataclass(frozen=True)
class Piece:
    side: Side
    kind: PieceKind

    def __post_init__(self) -> None:
        object.__setattr__(self, "side", Side(self.side))
        object.__setattr__(self, "kind", PieceKind(self.kind))


Board: TypeAlias = tuple[tuple[Piece | None, ...], ...]


@dataclass(frozen=True)
class Move:
    origin: Square
    destination: Square

    def __post_init__(self) -> None:
        if len(self.origin) != 2 or len(self.destination) != 2:
            raise ValueError("A square must contain a row and a column")
        if self.origin == self.destination:
            raise ValueError("A move must change squares")


@dataclass(frozen=True)
class XiangqiState:
    """Immutable Xiangqi position and the history needed for repetition draws."""

    board: Board
    turn: Side = Side.RED
    halfmove_clock: int = 0
    fullmove_number: int = 1
    position_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        rows = tuple(tuple(row) for row in self.board)
        object.__setattr__(self, "board", rows)
        object.__setattr__(self, "turn", Side(self.turn))

        if len(rows) != BOARD_ROWS or any(len(row) != BOARD_COLUMNS for row in rows):
            raise ValueError("A Xiangqi board must have 10 rows and 9 columns")
        if self.halfmove_clock < 0:
            raise ValueError("The halfmove clock cannot be negative")
        if self.fullmove_number < 1:
            raise ValueError("The fullmove number must be positive")

        general_counts = {Side.RED: 0, Side.BLACK: 0}
        for row in rows:
            for piece in row:
                if piece is not None and not isinstance(piece, Piece):
                    raise ValueError("Board squares must contain Piece instances or None")
                if piece is not None and piece.kind is PieceKind.GENERAL:
                    general_counts[piece.side] += 1
        if any(count != 1 for count in general_counts.values()):
            raise ValueError("A valid Xiangqi position must contain one general per side")

        history = tuple(self.position_history)
        current_key = _position_key(rows, self.turn)
        if not history:
            history = (current_key,)
        elif history[-1] != current_key:
            raise ValueError("The last history entry must match the current position")
        object.__setattr__(self, "position_history", history)

    @classmethod
    def initial(cls) -> XiangqiState:
        return cls.from_fen(STARTING_FEN)

    @classmethod
    def from_fen(cls, fen: str) -> XiangqiState:
        """Parse the six-field WXF Xiangqi FEN representation."""
        fields = fen.strip().split()
        if len(fields) != 6:
            raise ValueError("Xiangqi FEN must contain six fields")

        placement, active_color, castling, en_passant, halfmove, fullmove = fields
        if active_color not in {Side.RED.value, Side.BLACK.value}:
            raise ValueError("FEN active color must be 'w' or 'b'")
        if castling != "-" or en_passant != "-":
            raise ValueError("Xiangqi FEN castling and en-passant fields must be '-' ")

        try:
            halfmove_clock = int(halfmove)
            fullmove_number = int(fullmove)
        except ValueError as exc:
            raise ValueError("FEN move counters must be integers") from exc
        if halfmove_clock < 0 or fullmove_number < 1:
            raise ValueError("FEN move counters are outside their valid range")

        ranks = placement.split("/")
        if len(ranks) != BOARD_ROWS:
            raise ValueError("FEN piece placement must contain 10 ranks")

        board: list[list[Piece | None]] = []
        for rank in ranks:
            row: list[Piece | None] = []
            for symbol in rank:
                if symbol in "123456789":
                    row.extend([None] * int(symbol))
                    continue
                kind = _FEN_KIND_BY_LETTER.get(symbol.upper())
                if kind is None or not symbol.isascii() or not symbol.isalpha():
                    raise ValueError(f"Invalid FEN piece symbol: {symbol!r}")
                side = Side.RED if symbol.isupper() else Side.BLACK
                row.append(Piece(side, kind))
                if len(row) > BOARD_COLUMNS:
                    raise ValueError("A FEN rank cannot exceed 9 files")
            if len(row) != BOARD_COLUMNS:
                raise ValueError("Every FEN rank must describe exactly 9 files")
            board.append(row)

        return cls(
            board=tuple(tuple(row) for row in board),
            turn=Side(active_color),
            halfmove_clock=halfmove_clock,
            fullmove_number=fullmove_number,
        )

    @property
    def position_key(self) -> str:
        return _position_key(self.board, self.turn)

    def to_fen(self) -> str:
        placement = _board_to_placement(self.board)
        return (
            f"{placement} {self.turn.value} - - "
            f"{self.halfmove_clock} {self.fullmove_number}"
        )


_FEN_KIND_BY_LETTER = {kind.value: kind for kind in PieceKind}
_ORTHOGONAL_STEPS: tuple[Square, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))
_DIAGONAL_STEPS: tuple[Square, ...] = ((1, 1), (1, -1), (-1, 1), (-1, -1))
_HORSE_STEPS: tuple[Square, ...] = (
    (2, 1),
    (2, -1),
    (-2, 1),
    (-2, -1),
    (1, 2),
    (1, -2),
    (-1, 2),
    (-1, -2),
)


def _inside(square: Square) -> bool:
    row, column = square
    return 0 <= row < BOARD_ROWS and 0 <= column < BOARD_COLUMNS


def _inside_palace(side: Side, square: Square) -> bool:
    row, column = square
    if not 3 <= column <= 5:
        return False
    return row <= 2 if side is Side.BLACK else row >= 7


def _on_own_side_of_river(side: Side, row: int) -> bool:
    return row <= 4 if side is Side.BLACK else row >= 5


def _board_to_placement(board: Board) -> str:
    ranks: list[str] = []
    for row in board:
        symbols: list[str] = []
        empty_count = 0
        for piece in row:
            if piece is None:
                empty_count += 1
                continue
            if empty_count:
                symbols.append(str(empty_count))
                empty_count = 0
            letter = piece.kind.value
            symbols.append(letter if piece.side is Side.RED else letter.lower())
        if empty_count:
            symbols.append(str(empty_count))
        ranks.append("".join(symbols))
    return "/".join(ranks)


def _position_key(board: Board, turn: Side) -> str:
    return f"{_board_to_placement(board)} {turn.value}"


def _find_general(board: Board, side: Side) -> Square:
    for row_index, row in enumerate(board):
        for column_index, piece in enumerate(row):
            if piece is not None and piece.side is side and piece.kind is PieceKind.GENERAL:
                return row_index, column_index
    raise ValueError(f"No {side.name.lower()} general is present on the board")


def _candidate_destination(board: Board, side: Side, square: Square) -> Iterator[Square]:
    if not _inside(square):
        return
    target = board[square[0]][square[1]]
    if target is None or target.side is not side:
        yield square


def _piece_destinations(board: Board, origin: Square, piece: Piece) -> Iterator[Square]:
    row, column = origin

    if piece.kind is PieceKind.GENERAL:
        for row_step, column_step in _ORTHOGONAL_STEPS:
            destination = (row + row_step, column + column_step)
            if _inside_palace(piece.side, destination):
                yield from _candidate_destination(board, piece.side, destination)
        return

    if piece.kind is PieceKind.ADVISOR:
        for row_step, column_step in _DIAGONAL_STEPS:
            destination = (row + row_step, column + column_step)
            if _inside_palace(piece.side, destination):
                yield from _candidate_destination(board, piece.side, destination)
        return

    if piece.kind is PieceKind.ELEPHANT:
        for row_step, column_step in _DIAGONAL_STEPS:
            destination = (row + 2 * row_step, column + 2 * column_step)
            eye = (row + row_step, column + column_step)
            if (
                _inside(destination)
                and _on_own_side_of_river(piece.side, destination[0])
                and board[eye[0]][eye[1]] is None
            ):
                yield from _candidate_destination(board, piece.side, destination)
        return

    if piece.kind is PieceKind.HORSE:
        for row_step, column_step in _HORSE_STEPS:
            if abs(row_step) == 2:
                leg = (row + (1 if row_step > 0 else -1), column)
            else:
                leg = (row, column + (1 if column_step > 0 else -1))
            destination = (row + row_step, column + column_step)
            if _inside(destination) and board[leg[0]][leg[1]] is None:
                yield from _candidate_destination(board, piece.side, destination)
        return

    if piece.kind in {PieceKind.ROOK, PieceKind.CANNON}:
        for row_step, column_step in _ORTHOGONAL_STEPS:
            screen_found = False
            next_row, next_column = row + row_step, column + column_step
            while _inside((next_row, next_column)):
                destination = (next_row, next_column)
                target = board[next_row][next_column]
                if piece.kind is PieceKind.ROOK:
                    if target is None:
                        yield destination
                    else:
                        if target.side is not piece.side:
                            yield destination
                        break
                elif not screen_found:
                    if target is None:
                        yield destination
                    else:
                        screen_found = True
                elif target is not None:
                    if target.side is not piece.side:
                        yield destination
                    break
                next_row += row_step
                next_column += column_step
        return

    if piece.kind is PieceKind.PAWN:
        forward = -1 if piece.side is Side.RED else 1
        yield from _candidate_destination(board, piece.side, (row + forward, column))
        crossed_river = row <= 4 if piece.side is Side.RED else row >= 5
        if crossed_river:
            yield from _candidate_destination(board, piece.side, (row, column - 1))
            yield from _candidate_destination(board, piece.side, (row, column + 1))


def _generals_face_on_board(board: Board) -> bool:
    red_general = _find_general(board, Side.RED)
    black_general = _find_general(board, Side.BLACK)
    if red_general[1] != black_general[1]:
        return False
    start = min(red_general[0], black_general[0]) + 1
    end = max(red_general[0], black_general[0])
    return all(board[row][red_general[1]] is None for row in range(start, end))


def _is_square_attacked_on_board(board: Board, square: Square, by_side: Side) -> bool:
    if not _inside(square):
        return False
    for row_index, row in enumerate(board):
        for column_index, piece in enumerate(row):
            if piece is None or piece.side is not by_side:
                continue
            if square in _piece_destinations(board, (row_index, column_index), piece):
                return True

    target = board[square[0]][square[1]]
    if target is not None and target.kind is PieceKind.GENERAL and target.side is not by_side:
        return _generals_face_on_board(board)
    return False


def legal_moves(
    state: XiangqiState,
    *,
    side: Side | None = None,
    origin: Square | None = None,
) -> list[Move]:
    """Return legal moves for ``side`` (the active side by default)."""
    mover = state.turn if side is None else Side(side)
    if origin is not None and not _inside(origin):
        return []

    result: list[Move] = []
    for row_index, row in enumerate(state.board):
        for column_index, piece in enumerate(row):
            current = (row_index, column_index)
            if piece is None or piece.side is not mover:
                continue
            if origin is not None and current != origin:
                continue

            for destination in _piece_destinations(state.board, current, piece):
                target = state.board[destination[0]][destination[1]]
                # A Xiangqi game ends by checkmate or immobility, not by capturing a general.
                if target is not None and target.kind is PieceKind.GENERAL:
                    continue

                next_board_list = [list(board_row) for board_row in state.board]
                next_board_list[current[0]][current[1]] = None
                next_board_list[destination[0]][destination[1]] = piece
                next_board = tuple(tuple(board_row) for board_row in next_board_list)
                general_square = (
                    destination
                    if piece.kind is PieceKind.GENERAL
                    else _find_general(next_board, mover)
                )
                if not _is_square_attacked_on_board(next_board, general_square, mover.opponent):
                    result.append(Move(current, destination))
    return result


def legal_moves_from(state: XiangqiState, origin: Square) -> list[Move]:
    """Return legal moves for the active side's piece on ``origin``."""
    return legal_moves(state, origin=origin)


def is_square_attacked(state: XiangqiState, square: Square, by_side: Side) -> bool:
    """Check whether ``by_side`` attacks a square using Xiangqi movement rules."""
    return _is_square_attacked_on_board(state.board, square, Side(by_side))


def generals_face(state: XiangqiState) -> bool:
    """Return whether the two generals share an unobstructed file."""
    return _generals_face_on_board(state.board)


def is_in_check(state: XiangqiState, side: Side | None = None) -> bool:
    checked_side = state.turn if side is None else Side(side)
    general_square = _find_general(state.board, checked_side)
    return is_square_attacked(state, general_square, checked_side.opponent)


def apply_move(state: XiangqiState, move: Move) -> XiangqiState:
    """Apply a legal move and return a new immutable state."""
    if move not in legal_moves(state):
        raise ValueError(f"Illegal move: {move.origin} -> {move.destination}")

    origin_row, origin_column = move.origin
    target_row, target_column = move.destination
    moving_piece = state.board[origin_row][origin_column]
    if moving_piece is None:  # The legal-move check above makes this defensive only.
        raise ValueError("The origin square is empty")
    captured_piece = state.board[target_row][target_column]

    rows = [list(row) for row in state.board]
    rows[origin_row][origin_column] = None
    rows[target_row][target_column] = moving_piece
    next_board = tuple(tuple(row) for row in rows)
    next_turn = state.turn.opponent
    next_halfmove = (
        0
        if captured_piece is not None or moving_piece.kind is PieceKind.PAWN
        else state.halfmove_clock + 1
    )
    next_fullmove = state.fullmove_number + (1 if state.turn is Side.BLACK else 0)
    next_key = _position_key(next_board, next_turn)
    return XiangqiState(
        board=next_board,
        turn=next_turn,
        halfmove_clock=next_halfmove,
        fullmove_number=next_fullmove,
        position_history=state.position_history + (next_key,),
    )


def is_checkmate(state: XiangqiState, side: Side | None = None) -> bool:
    checked_side = state.turn if side is None else Side(side)
    return is_in_check(state, checked_side) and not legal_moves(state, side=checked_side)


def is_stalemate(state: XiangqiState, side: Side | None = None) -> bool:
    """Xiangqi stalemate means no legal move; it is a loss, not a draw."""
    blocked_side = state.turn if side is None else Side(side)
    return not is_in_check(state, blocked_side) and not legal_moves(state, side=blocked_side)


def is_draw(state: XiangqiState) -> bool:
    """Detect bare-generals, fourfold repetition, and the 50-move FEN clock draw."""
    if not legal_moves(state):
        return False
    if state.halfmove_clock >= FEN_FIFTY_MOVE_LIMIT:
        return True
    if state.position_history.count(state.position_key) >= REPETITION_DRAW_OCCURRENCES:
        return True
    return all(
        piece is None or piece.kind is PieceKind.GENERAL
        for row in state.board
        for piece in row
    )


def game_status(state: XiangqiState) -> GameStatus:
    moves = legal_moves(state)
    if not moves:
        return GameStatus.CHECKMATE if is_in_check(state) else GameStatus.STALEMATE
    if is_draw(state):
        return GameStatus.DRAW
    if is_in_check(state):
        return GameStatus.CHECK
    return GameStatus.ACTIVE
