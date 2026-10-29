"""Unit tests for Xiangqi FEN, movement, legality, and game outcomes."""

from collections.abc import Iterable
from dataclasses import replace

import pytest

from app.xiangqi import (
    NATURAL_CHECK_LIMIT_PER_SIDE,
    NATURAL_MOVE_LIMIT_PER_SIDE,
    STARTING_FEN,
    ChaseThreat,
    GameStatus,
    Move,
    MoveRecord,
    Piece,
    PieceKind,
    Side,
    XiangqiState,
    apply_move,
    game_status,
    game_winner,
    generals_face,
    is_checkmate,
    is_draw,
    is_in_check,
    is_stalemate,
    legal_moves,
    legal_moves_from,
)


PiecePlacement = tuple[Side, PieceKind, tuple[int, int]]


def make_state(
    pieces: Iterable[PiecePlacement] = (),
    *,
    turn: Side = Side.RED,
    red_general: tuple[int, int] = (9, 3),
    black_general: tuple[int, int] = (0, 5),
    halfmove_clock: int = 0,
    fullmove_number: int = 1,
    natural_move_counts: tuple[int, int] = (0, 0),
    natural_check_counts: tuple[int, int] = (0, 0),
) -> XiangqiState:
    board: list[list[Piece | None]] = [[None] * 9 for _ in range(10)]
    placements = [
        (Side.RED, PieceKind.GENERAL, red_general),
        (Side.BLACK, PieceKind.GENERAL, black_general),
        *pieces,
    ]
    for side, kind, (row, column) in placements:
        if board[row][column] is not None:
            raise ValueError(f"Test setup has overlapping pieces at {(row, column)}")
        board[row][column] = Piece(side, kind)
    return XiangqiState(
        board=tuple(tuple(row) for row in board),
        turn=turn,
        halfmove_clock=halfmove_clock,
        fullmove_number=fullmove_number,
        natural_move_counts=natural_move_counts,
        natural_check_counts=natural_check_counts,
    )


def destinations(state: XiangqiState, origin: tuple[int, int]) -> set[tuple[int, int]]:
    return {move.destination for move in legal_moves_from(state, origin)}


def test_initial_board_and_wxf_fen_round_trip() -> None:
    state = XiangqiState.initial()

    assert len(state.board) == 10
    assert all(len(row) == 9 for row in state.board)
    assert sum(piece is not None for row in state.board for piece in row) == 32
    assert state.to_fen() == STARTING_FEN
    assert XiangqiState.from_fen(STARTING_FEN).to_fen() == STARTING_FEN


@pytest.mark.parametrize(
    "fen",
    [
        "9/9/9/9/9/9/9/9/9 w - - 0 1",
        "9/9/9/9/9/9/9/9/9/9 w - - 0",
        "10/9/9/9/9/9/9/9/4k4/4K4 w - - 0 1",
        "9/9/9/9/9/9/9/9/4k4/4K4 x - - 0 1",
        "9/9/9/9/9/9/9/9/4k4/4K4 w K - 0 1",
        "9/9/9/9/9/9/9/9/4k4/4K4 w - e3 0 1",
        "9/9/9/9/9/9/9/9/4k4/4K4 w - - -1 1",
    ],
)
def test_invalid_fen_is_rejected(fen: str) -> None:
    with pytest.raises(ValueError):
        XiangqiState.from_fen(fen)


def test_fen_preserves_active_side_and_move_counters() -> None:
    fen = STARTING_FEN.replace(" w - - 0 1", " b - - 17 23")
    state = XiangqiState.from_fen(fen)

    assert state.turn is Side.BLACK
    assert state.halfmove_clock == 17
    assert state.fullmove_number == 23
    assert state.to_fen() == fen


def test_general_is_confined_to_its_palace() -> None:
    state = make_state(
        red_general=(9, 4),
        black_general=(0, 4),
        pieces=[(Side.RED, PieceKind.PAWN, (5, 4))],
    )

    assert destinations(state, (9, 4)) == {(8, 4), (9, 3), (9, 5)}


def test_advisor_moves_diagonally_inside_the_palace() -> None:
    state = make_state(pieces=[(Side.RED, PieceKind.ADVISOR, (8, 4))])

    assert destinations(state, (8, 4)) == {(7, 3), (7, 5), (9, 5)}


def test_elephant_cannot_jump_over_a_blocked_eye() -> None:
    state = make_state(
        pieces=[
            (Side.RED, PieceKind.ELEPHANT, (7, 2)),
            (Side.RED, PieceKind.PAWN, (6, 1)),
        ]
    )

    moves = destinations(state, (7, 2))
    assert (5, 0) not in moves
    assert (5, 4) in moves


def test_elephant_cannot_cross_the_river() -> None:
    state = make_state(pieces=[(Side.RED, PieceKind.ELEPHANT, (5, 2))])

    assert destinations(state, (5, 2)) == {(7, 0), (7, 4)}


def test_horse_cannot_move_when_its_leg_is_blocked() -> None:
    state = make_state(
        pieces=[
            (Side.RED, PieceKind.HORSE, (5, 4)),
            (Side.RED, PieceKind.PAWN, (4, 4)),
        ]
    )

    moves = destinations(state, (5, 4))
    assert (3, 3) not in moves
    assert (3, 5) not in moves
    assert (7, 3) in moves
    assert (7, 5) in moves


def test_rook_stops_at_the_first_piece() -> None:
    state = make_state(
        pieces=[
            (Side.RED, PieceKind.ROOK, (5, 0)),
            (Side.RED, PieceKind.PAWN, (5, 2)),
            (Side.BLACK, PieceKind.PAWN, (5, 4)),
        ]
    )

    moves = destinations(state, (5, 0))
    assert (5, 1) in moves
    assert (5, 2) not in moves
    assert (5, 4) not in moves


def test_cannon_uses_exactly_one_screen_to_capture() -> None:
    state = make_state(
        pieces=[
            (Side.RED, PieceKind.CANNON, (4, 0)),
            (Side.RED, PieceKind.PAWN, (4, 2)),
            (Side.BLACK, PieceKind.PAWN, (4, 5)),
        ]
    )

    moves = destinations(state, (4, 0))
    assert (4, 1) in moves  # Quiet moves before the screen are allowed.
    assert (4, 3) not in moves
    assert (4, 4) not in moves
    assert (4, 5) in moves  # One screen, then the first enemy piece.


def test_cannon_cannot_capture_without_a_screen() -> None:
    state = make_state(
        pieces=[
            (Side.RED, PieceKind.CANNON, (4, 0)),
            (Side.BLACK, PieceKind.PAWN, (4, 3)),
        ]
    )

    assert (4, 3) not in destinations(state, (4, 0))


def test_cannon_cannot_jump_a_second_piece_to_capture() -> None:
    state = make_state(
        pieces=[
            (Side.RED, PieceKind.CANNON, (4, 0)),
            (Side.RED, PieceKind.PAWN, (4, 1)),
            (Side.BLACK, PieceKind.PAWN, (4, 2)),
            (Side.BLACK, PieceKind.PAWN, (4, 4)),
        ]
    )

    moves = destinations(state, (4, 0))
    assert (4, 2) in moves
    assert (4, 4) not in moves


@pytest.mark.parametrize(
    ("side", "origin", "expected"),
    [
        (Side.RED, (6, 4), {(5, 4)}),
        (Side.BLACK, (3, 4), {(4, 4)}),
        (Side.RED, (4, 4), {(3, 4), (4, 3), (4, 5)}),
        (Side.BLACK, (5, 4), {(6, 4), (5, 3), (5, 5)}),
    ],
)
def test_pawn_moves_forward_and_sideways_only_after_crossing(
    side: Side,
    origin: tuple[int, int],
    expected: set[tuple[int, int]],
) -> None:
    state = make_state(
        pieces=[(side, PieceKind.PAWN, origin)],
        turn=side,
    )

    assert destinations(state, origin) == expected


def test_facing_generals_are_in_check() -> None:
    state = make_state(red_general=(9, 4), black_general=(0, 4))

    assert generals_face(state)
    assert is_in_check(state, Side.RED)
    assert is_in_check(state, Side.BLACK)


def test_legal_move_cannot_expose_facing_generals() -> None:
    state = make_state(
        red_general=(9, 4),
        black_general=(0, 4),
        pieces=[(Side.RED, PieceKind.PAWN, (4, 4))],
    )

    assert not generals_face(state)
    assert destinations(state, (4, 4)) == {(3, 4)}


def test_cannon_checks_general_only_when_there_is_one_screen() -> None:
    one_screen = make_state(
        red_general=(9, 3),
        black_general=(0, 4),
        pieces=[
            (Side.RED, PieceKind.CANNON, (5, 4)),
            (Side.RED, PieceKind.PAWN, (3, 4)),
        ],
        turn=Side.BLACK,
    )
    no_screen = make_state(
        red_general=(9, 3),
        black_general=(0, 4),
        pieces=[(Side.RED, PieceKind.CANNON, (5, 4))],
        turn=Side.BLACK,
    )
    two_screens = make_state(
        red_general=(9, 3),
        black_general=(0, 4),
        pieces=[
            (Side.RED, PieceKind.CANNON, (5, 4)),
            (Side.RED, PieceKind.PAWN, (3, 4)),
            (Side.RED, PieceKind.PAWN, (2, 4)),
        ],
        turn=Side.BLACK,
    )

    assert is_in_check(one_screen, Side.BLACK)
    assert not is_in_check(no_screen, Side.BLACK)
    assert not is_in_check(two_screens, Side.BLACK)


def test_player_can_escape_or_block_a_check() -> None:
    state = make_state(
        red_general=(9, 3),
        black_general=(0, 4),
        pieces=[
            (Side.RED, PieceKind.ROOK, (4, 4)),
            (Side.BLACK, PieceKind.ROOK, (2, 3)),
        ],
        turn=Side.BLACK,
    )

    assert is_in_check(state)
    moves = set(legal_moves(state))
    assert Move((0, 4), (0, 3)) in moves
    assert Move((0, 4), (0, 5)) in moves
    assert Move((0, 4), (1, 4)) not in moves
    assert Move((2, 3), (2, 4)) in moves


def test_checkmate_when_checked_side_has_no_legal_moves() -> None:
    state = make_state(
        red_general=(9, 3),
        black_general=(0, 4),
        pieces=[
            (Side.RED, PieceKind.ROOK, (0, 3)),
            (Side.RED, PieceKind.ROOK, (0, 6)),
            (Side.RED, PieceKind.ROOK, (2, 4)),
        ],
        turn=Side.BLACK,
    )

    assert is_in_check(state)
    assert is_checkmate(state)
    assert game_status(state) is GameStatus.CHECKMATE


def test_stalemate_is_a_loss_not_a_draw_in_xiangqi() -> None:
    state = make_state(
        red_general=(9, 3),
        black_general=(0, 4),
        pieces=[
            (Side.RED, PieceKind.PAWN, (1, 3)),
            (Side.RED, PieceKind.PAWN, (1, 5)),
            (Side.RED, PieceKind.PAWN, (2, 4)),
        ],
        turn=Side.BLACK,
        natural_move_counts=(NATURAL_MOVE_LIMIT_PER_SIDE,) * 2,
    )

    assert not is_in_check(state)
    assert is_stalemate(state)
    assert not is_draw(state)
    assert game_status(state) is GameStatus.STALEMATE


def test_repeated_position_is_a_draw_after_four_occurrences() -> None:
    state = XiangqiState.initial()
    cycle = (
        Move((9, 1), (7, 0)),
        Move((0, 1), (2, 0)),
        Move((7, 0), (9, 1)),
        Move((2, 0), (0, 1)),
    )
    for _ in range(3):
        for move in cycle:
            state = apply_move(state, move)

    assert state.position_history.count(state.position_key) == 4
    assert is_draw(state)
    assert game_status(state) is GameStatus.DRAW


def test_perpetual_check_is_a_loss_after_threefold_repetition() -> None:
    state = make_state(
        red_general=(9, 5),
        black_general=(0, 3),
        pieces=[(Side.RED, PieceKind.ROOK, (4, 4))],
    )
    cycle = (
        Move((4, 4), (4, 3)),
        Move((0, 3), (0, 4)),
        Move((4, 3), (4, 4)),
        Move((0, 4), (0, 3)),
    )
    for _ in range(2):
        for move in cycle:
            state = apply_move(state, move)

    assert state.position_history.count(state.position_key) == 3
    assert game_status(state) is GameStatus.PERPETUAL_CHECK_LOSS
    assert game_winner(state) is Side.BLACK
    assert not is_draw(state)


def repeated_chase_state(
    *,
    real_root: bool = False,
    chaser_kind: PieceKind = PieceKind.HORSE,
    target_kind: PieceKind = PieceKind.ROOK,
    target_is_unadvanced_pawn: bool = False,
) -> XiangqiState:
    state = make_state(
        pieces=[
            (Side.RED, chaser_kind, (4, 4)),
            (Side.BLACK, target_kind, (4, 6)),
        ]
    )
    chaser = state.board[4][4]
    target = state.board[4][6]
    assert chaser is not None and chaser.identity is not None
    assert target is not None and target.identity is not None
    threat = ChaseThreat(
        target_id=target.identity,
        target_kind=target.kind,
        target_is_unadvanced_pawn=target_is_unadvanced_pawn,
        chaser_ids=(chaser.identity,),
        chaser_kinds=(chaser.kind,),
        has_real_root=real_root,
    )
    records = (
        MoveRecord(Side.RED, Move((4, 4), (3, 2)), chaser.identity, False),
        MoveRecord(
            Side.BLACK,
            Move((4, 6), (5, 4)),
            target.identity,
            False,
            (threat,),
            chased_by=Side.RED,
        ),
        MoveRecord(Side.RED, Move((3, 2), (4, 4)), chaser.identity, False),
        MoveRecord(
            Side.BLACK,
            Move((5, 4), (4, 6)),
            target.identity,
            False,
            (threat,),
            chased_by=Side.RED,
        ),
    )
    repeated_positions = (
        state.position_key,
        "repeated-position-a",
        state.position_key,
        "repeated-position-b",
        state.position_key,
    )
    return replace(state, position_history=repeated_positions, move_history=records)


def test_perpetual_chase_of_unprotected_different_piece_loses() -> None:
    state = repeated_chase_state()

    assert game_status(state) is GameStatus.PERPETUAL_CHASE_LOSS
    assert game_winner(state) is Side.BLACK


def test_perpetual_chase_of_a_piece_with_a_real_root_draws() -> None:
    state = repeated_chase_state(real_root=True)

    assert game_status(state) is GameStatus.DRAW


def test_perpetual_same_type_chase_draws() -> None:
    state = repeated_chase_state(
        chaser_kind=PieceKind.ROOK,
        target_kind=PieceKind.ROOK,
    )

    assert game_status(state) is GameStatus.DRAW


def test_perpetual_pawn_chase_is_not_a_loss() -> None:
    state = repeated_chase_state(chaser_kind=PieceKind.PAWN)

    assert game_status(state) is GameStatus.DRAW


def test_unadvanced_enemy_pawn_is_not_a_chase_target() -> None:
    state = repeated_chase_state(
        target_kind=PieceKind.PAWN,
        target_is_unadvanced_pawn=True,
    )

    assert game_status(state) is GameStatus.ACTIVE


def test_chase_is_recorded_when_defender_moves_the_target_away() -> None:
    state = make_state(
        pieces=[
            (Side.RED, PieceKind.ROOK, (5, 0)),
            (Side.BLACK, PieceKind.HORSE, (5, 3)),
        ],
        turn=Side.BLACK,
    )
    target = state.board[5][3]
    assert target is not None and target.identity is not None

    after_evasion = apply_move(state, Move((5, 3), (3, 2)))
    response = after_evasion.move_history[-1]

    assert response.chased_by is Side.RED
    assert {threat.target_id for threat in response.chased_targets} == {target.identity}


def test_wxf_natural_move_count_requires_100_counted_moves_per_side() -> None:
    state = replace(XiangqiState.initial(), natural_move_counts=(99, 99))
    after_red = apply_move(state, Move((9, 1), (7, 0)))
    after_black = apply_move(after_red, Move((0, 1), (2, 0)))

    assert after_red.natural_move_counts == (100, 99)
    assert not is_draw(after_red)
    assert after_black.natural_move_counts == (100, 100)
    assert is_draw(after_black)


def test_check_moves_after_ten_checks_do_not_count_toward_natural_limit() -> None:
    state = make_state(
        red_general=(9, 5),
        black_general=(0, 3),
        pieces=[(Side.RED, PieceKind.ROOK, (4, 4))],
        natural_move_counts=(99, 0),
        natural_check_counts=(NATURAL_CHECK_LIMIT_PER_SIDE, 0),
    )

    after_check = apply_move(state, Move((4, 4), (4, 3)))

    assert after_check.move_history[-1].gives_check
    assert after_check.natural_move_counts == (99, 0)
    assert after_check.natural_check_counts == (10, 0)


def test_pawn_moves_and_captures_reset_the_halfmove_clock() -> None:
    pawn_state = XiangqiState.from_fen(
        STARTING_FEN.replace(" w - - 0 1", " w - - 49 1")
    )
    after_pawn_move = apply_move(pawn_state, Move((6, 0), (5, 0)))
    capture_state = make_state(
        pieces=[
            (Side.RED, PieceKind.ROOK, (5, 0)),
            (Side.BLACK, PieceKind.PAWN, (5, 1)),
        ],
        halfmove_clock=49,
        natural_move_counts=(50, 60),
        natural_check_counts=(3, 4),
    )
    after_capture = apply_move(capture_state, Move((5, 0), (5, 1)))

    assert after_pawn_move.halfmove_clock == 0
    assert after_capture.halfmove_clock == 0
    assert after_capture.natural_move_counts == (0, 0)
    assert after_capture.natural_check_counts == (0, 0)


def test_move_updates_side_to_move_and_fen_fullmove_number() -> None:
    state = XiangqiState.initial()
    after_red = apply_move(state, Move((9, 1), (7, 0)))
    after_black = apply_move(after_red, Move((0, 1), (2, 0)))

    assert after_red.turn is Side.BLACK
    assert after_red.fullmove_number == 1
    assert after_black.turn is Side.RED
    assert after_black.fullmove_number == 2
    assert XiangqiState.from_fen(after_black.to_fen()).to_fen() == after_black.to_fen()


def test_illegal_move_is_rejected() -> None:
    state = XiangqiState.initial()

    with pytest.raises(ValueError, match="Illegal move"):
        apply_move(state, Move((9, 1), (6, 1)))
