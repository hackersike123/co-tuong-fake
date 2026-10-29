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
REPETITION_DRAW_OCCURRENCES = 4
REPETITION_ADJUDICATION_OCCURRENCES = 3
NATURAL_MOVE_LIMIT_PER_SIDE = 100
NATURAL_CHECK_LIMIT_PER_SIDE = 10

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
    PERPETUAL_CHECK_LOSS = "perpetual_check_loss"
    PERPETUAL_CHASE_LOSS = "perpetual_chase_loss"


@dataclass(frozen=True)
class Piece:
    side: Side
    kind: PieceKind
    identity: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "side", Side(self.side))
        object.__setattr__(self, "kind", PieceKind(self.kind))
        if self.identity is not None and self.identity < 1:
            raise ValueError("Piece identity must be a positive integer")


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
class ChaseThreat:
    """A legal next-move capture threat recorded for WXF repetition ruling."""

    target_id: int
    target_kind: PieceKind
    target_is_unadvanced_pawn: bool
    chaser_ids: tuple[int, ...]
    chaser_kinds: tuple[PieceKind, ...]
    has_real_root: bool
    target_is_pinned: bool = False
    target_is_blocked_horse: bool = False
    has_unimpeded_horse_chaser: bool = False


@dataclass(frozen=True)
class MoveRecord:
    mover: Side
    move: Move
    moved_piece_id: int
    gives_check: bool
    chased_targets: tuple[ChaseThreat, ...] = ()
    captured_piece_id: int | None = None
    chased_by: Side | None = None
    captured_piece: Piece | None = None
    previous_halfmove_clock: int | None = None
    previous_natural_move_counts: tuple[int, int] | None = None
    previous_natural_check_counts: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mover", Side(self.mover))
        if self.chased_by is not None:
            object.__setattr__(self, "chased_by", Side(self.chased_by))


@dataclass(frozen=True)
class XiangqiState:
    """Immutable Xiangqi position and move history for tournament rulings."""

    board: Board
    turn: Side = Side.RED
    halfmove_clock: int = 0
    fullmove_number: int = 1
    natural_move_counts: tuple[int, int] = (0, 0)
    natural_check_counts: tuple[int, int] = (0, 0)
    position_history: tuple[str, ...] = ()
    move_history: tuple[MoveRecord, ...] = ()

    def __post_init__(self) -> None:
        source_rows = tuple(tuple(row) for row in self.board)
        if len(source_rows) != BOARD_ROWS or any(
            len(row) != BOARD_COLUMNS for row in source_rows
        ):
            raise ValueError("A Xiangqi board must have 10 rows and 9 columns")
        if any(
            piece is not None and not isinstance(piece, Piece)
            for row in source_rows
            for piece in row
        ):
            raise ValueError("Board squares must contain Piece instances or None")

        identities = [
            piece.identity
            for row in source_rows
            for piece in row
            if piece is not None and piece.identity is not None
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("Piece identities must be unique within a position")
        next_identity = max(identities, default=0) + 1
        normalized_rows: list[tuple[Piece | None, ...]] = []
        for row in source_rows:
            normalized_row: list[Piece | None] = []
            for piece in row:
                if piece is not None and piece.identity is None:
                    piece = Piece(piece.side, piece.kind, next_identity)
                    next_identity += 1
                normalized_row.append(piece)
            normalized_rows.append(tuple(normalized_row))
        rows = tuple(normalized_rows)
        object.__setattr__(self, "board", rows)
        object.__setattr__(self, "turn", Side(self.turn))

        if self.halfmove_clock < 0:
            raise ValueError("The halfmove clock cannot be negative")
        if self.fullmove_number < 1:
            raise ValueError("The fullmove number must be positive")
        for counter_name in ("natural_move_counts", "natural_check_counts"):
            counters = tuple(getattr(self, counter_name))
            if len(counters) != 2 or any(count < 0 for count in counters):
                raise ValueError(f"{counter_name} must contain two nonnegative values")
            object.__setattr__(self, counter_name, counters)

        general_counts = {Side.RED: 0, Side.BLACK: 0}
        for row in rows:
            for piece in row:
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
        move_history = tuple(self.move_history)
        if len(move_history) != len(history) - 1:
            raise ValueError("Move history must contain one record per position transition")
        object.__setattr__(self, "position_history", history)
        object.__setattr__(self, "move_history", move_history)

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
    target = board[square[0]][square[1]]
    if target is not None and target.side is by_side:
        return False

    target_row, target_column = square
    for row_index, row in enumerate(board):
        for column_index, piece in enumerate(row):
            if piece is None or piece.side is not by_side:
                continue

            row_delta = target_row - row_index
            column_delta = target_column - column_index
            absolute_row_delta = abs(row_delta)
            absolute_column_delta = abs(column_delta)

            if piece.kind is PieceKind.GENERAL:
                if (
                    absolute_row_delta + absolute_column_delta == 1
                    and _inside_palace(piece.side, square)
                ):
                    return True
                continue

            if piece.kind is PieceKind.ADVISOR:
                if (
                    absolute_row_delta == 1
                    and absolute_column_delta == 1
                    and _inside_palace(piece.side, square)
                ):
                    return True
                continue

            if piece.kind is PieceKind.ELEPHANT:
                if (
                    absolute_row_delta == 2
                    and absolute_column_delta == 2
                    and _on_own_side_of_river(piece.side, target_row)
                    and board[row_index + row_delta // 2][
                        column_index + column_delta // 2
                    ]
                    is None
                ):
                    return True
                continue

            if piece.kind is PieceKind.HORSE:
                if (absolute_row_delta, absolute_column_delta) not in {
                    (2, 1),
                    (1, 2),
                }:
                    continue
                if absolute_row_delta == 2:
                    leg = (row_index + row_delta // 2, column_index)
                else:
                    leg = (row_index, column_index + column_delta // 2)
                if board[leg[0]][leg[1]] is None:
                    return True
                continue

            if piece.kind in {PieceKind.ROOK, PieceKind.CANNON}:
                if row_delta != 0 and column_delta != 0:
                    continue
                row_step = (row_delta > 0) - (row_delta < 0)
                column_step = (column_delta > 0) - (column_delta < 0)
                current_row = row_index + row_step
                current_column = column_index + column_step
                screens = 0
                while (current_row, current_column) != square:
                    if board[current_row][current_column] is not None:
                        screens += 1
                    current_row += row_step
                    current_column += column_step

                if piece.kind is PieceKind.ROOK and screens == 0:
                    return True
                if piece.kind is PieceKind.CANNON and (
                    (screens == 0 and target is None)
                    or (screens == 1 and target is not None)
                ):
                    return True
                continue

            if piece.kind is PieceKind.PAWN:
                forward = -1 if piece.side is Side.RED else 1
                if row_delta == forward and column_delta == 0:
                    return True
                crossed_river = row_index <= 4 if piece.side is Side.RED else row_index >= 5
                if crossed_river and row_delta == 0 and absolute_column_delta == 1:
                    return True

    if target is not None and target.kind is PieceKind.GENERAL:
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


def _pawn_has_crossed_river(piece: Piece, row: int) -> bool:
    if piece.kind is not PieceKind.PAWN:
        return True
    return row <= 4 if piece.side is Side.RED else row >= 5


def _has_real_root(state: XiangqiState, capture_move: Move) -> bool:
    origin_row, origin_column = capture_move.origin
    target_row, target_column = capture_move.destination
    attacker = state.board[origin_row][origin_column]
    target = state.board[target_row][target_column]
    if attacker is None or target is None:
        return False

    rows = [list(row) for row in state.board]
    rows[origin_row][origin_column] = None
    rows[target_row][target_column] = attacker
    after_capture = XiangqiState(
        board=tuple(tuple(row) for row in rows),
        turn=target.side,
    )
    return any(
        move.destination == capture_move.destination
        for move in legal_moves(after_capture, side=target.side)
    )


_PIECE_VALUES = {
    PieceKind.GENERAL: 1000,
    PieceKind.ROOK: 90,
    PieceKind.CANNON: 45,
    PieceKind.HORSE: 45,
    PieceKind.ADVISOR: 20,
    PieceKind.ELEPHANT: 20,
    PieceKind.PAWN: 10,
}


def _is_protected_for_chase(state: XiangqiState, capture_move: Move) -> bool:
    attacker = state.board[capture_move.origin[0]][capture_move.origin[1]]
    target = state.board[capture_move.destination[0]][capture_move.destination[1]]
    if attacker is None or target is None:
        return False
    # WXF treats a favorable capture of a more valuable piece as an exchange,
    # even when that piece has a legal recapture.
    if _PIECE_VALUES[target.kind] > _PIECE_VALUES[attacker.kind]:
        return False
    return _has_real_root(state, capture_move)


def _find_piece_square(board: Board, identity: int) -> Square | None:
    for row_index, row in enumerate(board):
        for column_index, piece in enumerate(row):
            if piece is not None and piece.identity == identity:
                return row_index, column_index
    return None


def _piece_is_pinned(state: XiangqiState, identity: int) -> bool:
    origin = _find_piece_square(state.board, identity)
    if origin is None:
        return False
    piece = state.board[origin[0]][origin[1]]
    if piece is None or piece.kind is PieceKind.GENERAL:
        return False

    for destination in _piece_destinations(state.board, origin, piece):
        captured = state.board[destination[0]][destination[1]]
        if captured is not None and captured.kind is PieceKind.GENERAL:
            continue
        rows = [list(row) for row in state.board]
        rows[origin[0]][origin[1]] = None
        rows[destination[0]][destination[1]] = piece
        board = tuple(tuple(row) for row in rows)
        general = _find_general(board, piece.side)
        if _is_square_attacked_on_board(board, general, piece.side.opponent):
            return True
    return False


def _horse_has_blocked_leg(board: Board, origin: Square) -> bool:
    row, column = origin
    for row_step, column_step in _HORSE_STEPS:
        destination = (row + row_step, column + column_step)
        if not _inside(destination):
            continue
        if abs(row_step) == 2:
            leg = (row + (1 if row_step > 0 else -1), column)
        else:
            leg = (row, column + (1 if column_step > 0 else -1))
        if board[leg[0]][leg[1]] is not None:
            return True
    return False


def _chaser_has_unblocked_horse(board: Board, chaser_ids: tuple[int, ...]) -> bool:
    for identity in chaser_ids:
        square = _find_piece_square(board, identity)
        if square is None:
            continue
        piece = board[square[0]][square[1]]
        if piece is not None and piece.kind is PieceKind.HORSE:
            if not _horse_has_blocked_leg(board, square):
                return True
    return False


def _collect_chase_candidates(
    state: XiangqiState,
    chaser_side: Side,
) -> tuple[ChaseThreat, ...]:
    captures_by_target: dict[int, list[Move]] = {}
    target_pieces: dict[int, Piece] = {}
    for move in legal_moves(state, side=chaser_side):
        target_row, target_column = move.destination
        target = state.board[target_row][target_column]
        if target is None or target.side is chaser_side or target.kind is PieceKind.GENERAL:
            continue
        if target.identity is None:
            continue
        if target.kind is PieceKind.PAWN and not _pawn_has_crossed_river(
            target, target_row
        ):
            continue
        if _is_protected_for_chase(state, move):
            continue
        captures_by_target.setdefault(target.identity, []).append(move)
        target_pieces[target.identity] = target

    candidates: list[ChaseThreat] = []
    for target_id, capture_moves in captures_by_target.items():
        target = target_pieces[target_id]
        chasers: dict[int, PieceKind] = {}
        for move in capture_moves:
            attacker = state.board[move.origin[0]][move.origin[1]]
            if attacker is None or attacker.identity is None:
                continue
            chasers[attacker.identity] = attacker.kind
        if not chasers:
            continue
        candidates.append(
            ChaseThreat(
                target_id=target_id,
                target_kind=target.kind,
                target_is_unadvanced_pawn=False,
                chaser_ids=tuple(sorted(chasers)),
                chaser_kinds=tuple(chasers[chaser_id] for chaser_id in sorted(chasers)),
                has_real_root=False,
            )
        )
    return tuple(candidates)


def _resolve_chase_candidates(
    state: XiangqiState,
    chaser_side: Side,
    moved_piece_id: int,
    candidates: tuple[ChaseThreat, ...],
) -> tuple[ChaseThreat, ...]:
    if not candidates or is_in_check(state, state.turn):
        return ()

    legal_capture_moves = legal_moves(state, side=chaser_side)
    resolved: list[ChaseThreat] = []
    for candidate in candidates:
        target_square = _find_piece_square(state.board, candidate.target_id)
        if target_square is None:
            continue
        target = state.board[target_square[0]][target_square[1]]
        if target is None:
            continue

        surviving_chasers = {
            identity: kind
            for identity, kind in zip(candidate.chaser_ids, candidate.chaser_kinds)
            if _find_piece_square(state.board, identity) is not None
        }
        if not surviving_chasers:
            continue

        capture_moves = [
            move
            for move in legal_capture_moves
            if move.destination == target_square
            and state.board[move.origin[0]][move.origin[1]] is not None
            and state.board[move.origin[0]][move.origin[1]].identity
            in surviving_chasers
        ]
        target_moved_away = moved_piece_id == candidate.target_id
        real_root = any(_has_real_root(state, move) for move in capture_moves)
        # Record only an effective response: the victim moved, or it acquired
        # a legal recapture. A move that leaves an unprotected capture available
        # is not a chase response under the WXF definition.
        if not target_moved_away and not real_root:
            continue

        resolved.append(
            ChaseThreat(
                target_id=candidate.target_id,
                target_kind=target.kind,
                target_is_unadvanced_pawn=False,
                chaser_ids=tuple(sorted(surviving_chasers)),
                chaser_kinds=tuple(
                    surviving_chasers[identity] for identity in sorted(surviving_chasers)
                ),
                has_real_root=real_root,
                target_is_pinned=_piece_is_pinned(state, candidate.target_id),
                target_is_blocked_horse=(
                    target.kind is PieceKind.HORSE
                    and _horse_has_blocked_leg(state.board, target_square)
                ),
                has_unimpeded_horse_chaser=_chaser_has_unblocked_horse(
                    state.board,
                    tuple(sorted(surviving_chasers)),
                ),
            )
        )
    return tuple(resolved)


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
    moved_piece_id = moving_piece.identity
    if moved_piece_id is None:
        raise ValueError("A piece on the board must have an identity")

    irreversible_move = captured_piece is not None or moving_piece.kind is PieceKind.PAWN
    chase_candidates = (
        _collect_chase_candidates(state, state.turn.opponent)
        if not irreversible_move and not is_in_check(state, state.turn)
        else ()
    )

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

    provisional = XiangqiState(
        board=next_board,
        turn=next_turn,
        halfmove_clock=next_halfmove,
        fullmove_number=next_fullmove,
    )
    gives_check = is_in_check(provisional, next_turn)

    if captured_piece is not None:
        natural_move_counts = (0, 0)
        natural_check_counts = (0, 0)
    else:
        side_index = 0 if state.turn is Side.RED else 1
        move_counts = list(state.natural_move_counts)
        check_counts = list(state.natural_check_counts)
        if not gives_check or check_counts[side_index] < NATURAL_CHECK_LIMIT_PER_SIDE:
            move_counts[side_index] += 1
            if gives_check:
                check_counts[side_index] += 1
        natural_move_counts = tuple(move_counts)
        natural_check_counts = tuple(check_counts)

    chased_targets = (
        _resolve_chase_candidates(
            provisional,
            next_turn,
            moved_piece_id,
            chase_candidates,
        )
        if not irreversible_move and not gives_check
        else ()
    )
    move_record = MoveRecord(
        mover=state.turn,
        move=move,
        moved_piece_id=moved_piece_id,
        gives_check=gives_check,
        chased_targets=chased_targets,
        captured_piece_id=(
            captured_piece.identity if captured_piece is not None else None
        ),
        chased_by=state.turn.opponent if chased_targets else None,
        captured_piece=captured_piece,
        previous_halfmove_clock=state.halfmove_clock,
        previous_natural_move_counts=state.natural_move_counts,
        previous_natural_check_counts=state.natural_check_counts,
    )
    return XiangqiState(
        board=next_board,
        turn=next_turn,
        halfmove_clock=next_halfmove,
        fullmove_number=next_fullmove,
        natural_move_counts=natural_move_counts,
        natural_check_counts=natural_check_counts,
        position_history=state.position_history + (next_key,),
        move_history=state.move_history + (move_record,),
    )


def make_move(state: XiangqiState, move: Move) -> XiangqiState:
    """Apply a legal move and return the resulting immutable game state."""
    return apply_move(state, move)


def undo_move(state: XiangqiState) -> XiangqiState:
    """Return the state immediately before the most recently applied move."""
    if not state.move_history:
        raise ValueError("There is no move to undo")

    record = state.move_history[-1]
    if (
        record.previous_halfmove_clock is None
        or record.previous_natural_move_counts is None
        or record.previous_natural_check_counts is None
    ):
        raise ValueError("The latest move record does not contain undo data")
    if state.turn is not record.mover.opponent:
        raise ValueError("The latest move record does not match the active side")

    origin_row, origin_column = record.move.origin
    target_row, target_column = record.move.destination
    rows = [list(row) for row in state.board]
    moved_piece = rows[target_row][target_column]
    if moved_piece is None or moved_piece.identity != record.moved_piece_id:
        raise ValueError("The latest move does not match the current board")
    if rows[origin_row][origin_column] is not None:
        raise ValueError("The move origin is occupied and cannot be restored")
    captured_piece_id = (
        record.captured_piece.identity if record.captured_piece is not None else None
    )
    if captured_piece_id != record.captured_piece_id:
        raise ValueError("The captured piece does not match the move record")

    rows[origin_row][origin_column] = moved_piece
    rows[target_row][target_column] = record.captured_piece
    return XiangqiState(
        board=tuple(tuple(row) for row in rows),
        turn=record.mover,
        halfmove_clock=record.previous_halfmove_clock,
        fullmove_number=state.fullmove_number - (record.mover is Side.BLACK),
        natural_move_counts=record.previous_natural_move_counts,
        natural_check_counts=record.previous_natural_check_counts,
        position_history=state.position_history[:-1],
        move_history=state.move_history[:-1],
    )


def is_checkmate(state: XiangqiState, side: Side | None = None) -> bool:
    checked_side = state.turn if side is None else Side(side)
    return is_in_check(state, checked_side) and not legal_moves(state, side=checked_side)


def is_stalemate(state: XiangqiState, side: Side | None = None) -> bool:
    """Xiangqi stalemate means no legal move; it is a loss, not a draw."""
    blocked_side = state.turn if side is None else Side(side)
    return not is_in_check(state, blocked_side) and not legal_moves(state, side=blocked_side)


def _perpetual_chase_ruling(
    records: tuple[MoveRecord, ...],
    side: Side,
) -> GameStatus | None:
    if any(record.mover is side and record.gives_check for record in records):
        return None

    response_indexes = [
        index + 1
        for index, record in enumerate(records)
        if record.mover is side and index + 1 < len(records)
    ]
    if not response_indexes:
        return None
    response_records = [records[index] for index in response_indexes]
    if any(record.chased_by is not side for record in response_records):
        return None

    chase_sets = [
        {
            threat.target_id
            for threat in record.chased_targets
            if not threat.target_is_unadvanced_pawn
        }
        for record in response_records
    ]
    common_targets = set.intersection(*chase_sets) if chase_sets else set()

    # Repeatedly chasing several targets is not penalized as a perpetual single-piece chase.
    if all(len(targets) >= 2 for targets in chase_sets):
        return GameStatus.DRAW
    if not common_targets:
        return None
    if len(common_targets) > 1:
        return GameStatus.DRAW

    target_id = next(iter(common_targets))
    threats: list[ChaseThreat] = []
    for record in response_records:
        threat = next(
            (
                item
                for item in record.chased_targets
                if item.target_id == target_id
            ),
            None,
        )
        if threat is None:
            return None
        threats.append(threat)

    if all(threat.has_real_root for threat in threats):
        return GameStatus.DRAW

    chaser_ids = {chaser_id for threat in threats for chaser_id in threat.chaser_ids}
    chaser_kinds = {kind for threat in threats for kind in threat.chaser_kinds}
    if PieceKind.GENERAL in chaser_kinds or PieceKind.PAWN in chaser_kinds:
        return GameStatus.DRAW
    if any(
        threat.target_is_blocked_horse and threat.has_unimpeded_horse_chaser
        for threat in threats
    ):
        return GameStatus.PERPETUAL_CHASE_LOSS
    if any(threat.target_kind in threat.chaser_kinds for threat in threats):
        if any(threat.target_is_pinned for threat in threats):
            return GameStatus.PERPETUAL_CHASE_LOSS
        return GameStatus.DRAW

    # Article 20.3 penalizes multiple non-General/non-Pawn pieces chasing one target.
    if len(chaser_ids) > 1:
        return GameStatus.PERPETUAL_CHASE_LOSS
    return GameStatus.PERPETUAL_CHASE_LOSS


def _repetition_adjudication(
    state: XiangqiState,
) -> tuple[GameStatus, Side | None] | None:
    occurrences = [
        index
        for index, position in enumerate(state.position_history)
        if position == state.position_key
    ]
    if len(occurrences) < REPETITION_ADJUDICATION_OCCURRENCES:
        return None

    cycle_start, cycle_end = occurrences[-3], occurrences[-1]
    records = state.move_history[cycle_start:cycle_end]
    if len(records) != cycle_end - cycle_start or not records:
        if len(occurrences) >= REPETITION_DRAW_OCCURRENCES:
            return GameStatus.DRAW, None
        return None

    perpetual_checkers = {
        side
        for side in Side
        if (side_records := [record for record in records if record.mover is side])
        and all(record.gives_check for record in side_records)
    }
    if len(perpetual_checkers) == 2:
        return GameStatus.DRAW, None
    if len(perpetual_checkers) == 1:
        return GameStatus.PERPETUAL_CHECK_LOSS, next(iter(perpetual_checkers))

    chase_rulings = {
        side: _perpetual_chase_ruling(records, side)
        for side in Side
    }
    chase_losses = [
        side
        for side, ruling in chase_rulings.items()
        if ruling is GameStatus.PERPETUAL_CHASE_LOSS
    ]
    chase_draws = any(ruling is GameStatus.DRAW for ruling in chase_rulings.values())
    if chase_draws or len(chase_losses) == 2:
        return GameStatus.DRAW, None
    if chase_losses:
        return GameStatus.PERPETUAL_CHASE_LOSS, chase_losses[0]

    if len(occurrences) >= REPETITION_DRAW_OCCURRENCES:
        return GameStatus.DRAW, None
    return None


def _has_only_generals(state: XiangqiState) -> bool:
    return all(
        piece is None or piece.kind is PieceKind.GENERAL
        for row in state.board
        for piece in row
    )


def _natural_move_draw(state: XiangqiState) -> bool:
    return all(count >= NATURAL_MOVE_LIMIT_PER_SIDE for count in state.natural_move_counts)


def is_draw(state: XiangqiState) -> bool:
    """Detect WXF repetition rulings and automatic natural-movecount draws."""
    if not legal_moves(state):
        return False
    if _has_only_generals(state) or _natural_move_draw(state):
        return True
    adjudication = _repetition_adjudication(state)
    if adjudication is not None and adjudication[0] is GameStatus.DRAW:
        return True
    return False


def game_status(state: XiangqiState) -> GameStatus:
    moves = legal_moves(state)
    if not moves:
        return GameStatus.CHECKMATE if is_in_check(state) else GameStatus.STALEMATE

    adjudication = _repetition_adjudication(state)
    if adjudication is not None:
        return adjudication[0]
    if _has_only_generals(state) or _natural_move_draw(state):
        return GameStatus.DRAW
    if is_in_check(state):
        return GameStatus.CHECK
    return GameStatus.ACTIVE


def game_winner(state: XiangqiState) -> Side | None:
    """Return the winner for a terminal loss, or ``None`` while active/drawn."""
    status = game_status(state)
    if status in {GameStatus.CHECKMATE, GameStatus.STALEMATE}:
        return state.turn.opponent
    if status in {GameStatus.PERPETUAL_CHECK_LOSS, GameStatus.PERPETUAL_CHASE_LOSS}:
        adjudication = _repetition_adjudication(state)
        if adjudication is not None and adjudication[1] is not None:
            return adjudication[1].opponent
    return None
