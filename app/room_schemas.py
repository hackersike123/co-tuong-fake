"""Request and response models for public game rooms."""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class RoomCreateRequest(BaseModel):
    """Input used to create a public waiting room."""

    name: str = Field(min_length=1, max_length=80, examples=["Ván cờ cuối tuần"])
    host_name: str = Field(default="Khách", min_length=1, max_length=80, examples=["Minh Anh"])

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
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
    """Optional participant or invitation token used to join a room."""

    participant_token: str | None = Field(default=None, min_length=32, max_length=128)
    invite_token: str | None = Field(default=None, min_length=32, max_length=128)


class RoomCodeJoinRequest(RoomJoinRequest):
    """Numeric room code and optional tokens used from the public lobby."""

    room_code: str = Field(pattern=r"^[0-9]{1,10}$", examples=["123"])


class RoomActionRequest(BaseModel):
    """Capability token required for start and leave operations."""

    participant_token: str = Field(min_length=32, max_length=128)


class RoomInviteRequest(RoomActionRequest):
    """Host credentials and recipient address for a direct email invitation."""

    email: EmailStr


class RoomSummary(BaseModel):
    """Public room information safe to expose in the lobby."""

    id: int
    name: str
    host_name: str
    visibility: Literal["public"]
    status: Literal["waiting", "playing"]
    player_count: int
    spectator_count: int
    created_at: int


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
