"""Request and response models for public game rooms."""

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator


class RoomCreateRequest(BaseModel):
    """Input used to create a waiting room with lobby and access settings."""

    model_config = ConfigDict(populate_by_name=True)

    room_name: str = Field(
        min_length=1,
        max_length=80,
        validation_alias=AliasChoices("room_name", "name"),
        examples=["Weekend Xiangqi"],
    )
    host_name: str = Field(default="Khách", min_length=1, max_length=80, examples=["Minh Anh"])
    time_per_move: Literal[15, 30, 60] = Field(
        default=30,
        validation_alias=AliasChoices("time_per_move", "timer_seconds"),
    )
    is_public: bool = True
    password: str | None = Field(default=None, min_length=1, max_length=128, repr=False)
    allow_spectators: bool = True

    @field_validator("room_name")
    @classmethod
    def trim_room_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Room name cannot be blank")
        return name

    @field_validator("host_name")
    @classmethod
    def trim_host_name(cls, value: str) -> str:
        host_name = value.strip()
        if not host_name:
            raise ValueError("Host name cannot be blank")
        return host_name


class RoomJoinRequest(BaseModel):
    """Optional room password, invitation, or participant token."""

    participant_token: str | None = Field(default=None, min_length=32, max_length=128)
    invite_token: str | None = Field(default=None, min_length=32, max_length=128)
    password: str | None = Field(default=None, min_length=1, max_length=128, repr=False)


class RoomCodeJoinRequest(RoomJoinRequest):
    """Numeric room code and optional tokens used from the public lobby."""

    room_code: str = Field(pattern=r"^[0-9]{1,10}$", examples=["123"])


class RoomActionRequest(BaseModel):
    """Capability token required for start and leave operations."""

    participant_token: str = Field(min_length=32, max_length=128)


class RoomReadyRequest(RoomActionRequest):
    """Player two's ready state while the room is waiting."""

    ready: bool = True


class RoomInviteRequest(RoomActionRequest):
    """Host credentials and recipient address for a direct email invitation."""

    email: EmailStr


class RoomSummary(BaseModel):
    """Room information safe to expose in the lobby or join response."""

    id: int
    room_id: int
    room_uuid: str
    room_name: str
    name: str
    host_name: str
    visibility: Literal["public", "private"]
    is_public: bool
    has_password: bool
    allow_spectators: bool
    player2_ready: bool
    status: Literal["waiting", "playing", "finished"]
    player_count: int
    spectator_count: int
    created_at: int
    timer_seconds: Literal[15, 30, 60]
    time_per_move: Literal[15, 30, 60]


class RoomGameSnapshot(BaseModel):
    """Authoritative board and clock values for a started room."""

    room_id: int
    fen: str
    version: int
    side_to_move: Literal["w", "b"]
    red_time_ms: int
    black_time_ms: int
    timer_seconds: Literal[15, 30, 60]
    status: Literal["playing", "finished"]
    result: str | None = None
    reason: str | None = None
    winner: Literal["w", "b"] | None = None
    round_number: int = 0
    notation: str = ""
    draw_offer_by: Literal["player1", "player2"] | None = None
    rematch_requested_by: list[Literal["player1", "player2"]] = Field(
        default_factory=list
    )
    paused: bool = False
    disconnected_players: list[Literal["player1", "player2"]] = Field(default_factory=list)
    reconnect_deadlines_ms: dict[Literal["player1", "player2"], int] = Field(
        default_factory=dict
    )
    server_time_ms: int


class RoomMatchHistory(BaseModel):
    """Saved result and move notation for one completed room round."""

    id: int
    room_id: int
    room_uuid: str
    round_number: int
    room_name: str
    red_player: str
    black_player: str
    result: str
    reason: str | None
    winner: Literal["w", "b"] | None
    notation: str
    final_fen: str
    finished_at: datetime


class RoomMoveRequest(BaseModel):
    """Client move coordinates; all legality is checked on the server."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    from_square: tuple[int, int] = Field(alias="from")
    to_square: tuple[int, int] = Field(alias="to")


class RoomAccessResponse(RoomSummary):
    """Room details plus a participant capability token."""

    role: Literal["player1", "player2", "spectator"]
    participant_token: str
    join_url: str


class RoomLeaveResponse(BaseModel):
    """Result of leaving a room."""

    message: str
    room_deleted: bool


class RoomInviteResponse(BaseModel):
    message: str
    email: EmailStr
    room_code: str
    join_url: str
