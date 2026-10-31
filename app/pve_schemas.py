"""Pydantic request and response models for single-player games."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ai_engine import Difficulty, difficulty_settings
from .xiangqi import Side, STARTING_FEN, XiangqiState


class PveDifficultyOption(BaseModel):
    min_depth: int
    max_depth: int
    default_depth: int
    random_move_probability: float


class PveOptionsResponse(BaseModel):
    starting_fen: str = STARTING_FEN
    sides: list[Side] = [Side.RED, Side.BLACK]
    difficulties: dict[Difficulty, PveDifficultyOption]


class PveGameStartRequest(BaseModel):
    player_side: Side = Side.RED
    difficulty: Difficulty = Difficulty.MEDIUM
    depth: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def validate_depth_for_difficulty(self) -> "PveGameStartRequest":
        if self.depth is not None:
            settings = difficulty_settings(self.difficulty)
            if not settings.min_depth <= self.depth <= settings.max_depth:
                raise ValueError(
                    f"{self.difficulty.value} depth must be between "
                    f"{settings.min_depth} and {settings.max_depth}"
                )
        return self

    @property
    def selected_depth(self) -> int:
        return self.depth or difficulty_settings(self.difficulty).default_depth


class PveGameStartResponse(BaseModel):
    fen: str
    player_side: Side
    ai_side: Side
    side_to_move: Side
    difficulty: Difficulty
    depth: int


class PveAiMoveRequest(BaseModel):
    fen: str = Field(min_length=10, max_length=128)
    player_side: Side
    difficulty: Difficulty = Difficulty.MEDIUM
    depth: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def validate_position_and_depth(self) -> "PveAiMoveRequest":
        XiangqiState.from_fen(self.fen)
        if self.depth is not None:
            settings = difficulty_settings(self.difficulty)
            if not settings.min_depth <= self.depth <= settings.max_depth:
                raise ValueError(
                    f"{self.difficulty.value} depth must be between "
                    f"{settings.min_depth} and {settings.max_depth}"
                )
        return self

    @property
    def selected_depth(self) -> int:
        return self.depth or difficulty_settings(self.difficulty).default_depth


class PveSocketMoveRequest(BaseModel):
    """One Socket-style event payload carried by the existing WebSocket route."""

    model_config = ConfigDict(extra="forbid")

    game_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    fen: str = Field(min_length=10, max_length=128)
    player_side: Side = Side.RED
    difficulty: Difficulty = Difficulty.MEDIUM
    depth: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def validate_position_and_depth(self) -> "PveSocketMoveRequest":
        XiangqiState.from_fen(self.fen)
        if self.depth is not None:
            settings = difficulty_settings(self.difficulty)
            if not settings.min_depth <= self.depth <= settings.max_depth:
                raise ValueError(
                    f"{self.difficulty.value} depth must be between "
                    f"{settings.min_depth} and {settings.max_depth}"
                )
        return self

    @property
    def selected_depth(self) -> int:
        return self.depth or difficulty_settings(self.difficulty).default_depth


class PveMoveResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_square: tuple[int, int] = Field(serialization_alias="from")
    to_square: tuple[int, int] = Field(serialization_alias="to")


class PveAiMoveResponse(BaseModel):
    move: PveMoveResponse
    fen: str
    ai_side: Side
    difficulty: Difficulty
    depth: int
    score: int
    nodes: int
    cutoffs: int
    status: str | None = None
    winner: Side | None = None


class PvePlayerMoveRequest(BaseModel):
    """One player move to validate against the server's Xiangqi rules."""

    model_config = ConfigDict(populate_by_name=True)

    fen: str = Field(min_length=10, max_length=128)
    player_side: Side
    from_square: tuple[int, int] = Field(alias="from")
    to_square: tuple[int, int] = Field(alias="to")


class PvePlayerMoveResponse(BaseModel):
    fen: str
    player_side: Side
    side_to_move: Side
    status: str
    winner: Side | None = None
