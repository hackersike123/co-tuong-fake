"""Request and response models for public game rooms."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RoomCreateRequest(BaseModel):
    """Input used to create a public waiting room."""

    name: str = Field(min_length=1, max_length=80, examples=["Ván cờ cuối tuần"])

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Room name cannot be blank")
        return name


class RoomJoinRequest(BaseModel):
    """Optional existing token used to reconnect to a room."""

    participant_token: str | None = Field(default=None, min_length=32, max_length=128)


class RoomActionRequest(BaseModel):
    """Capability token required for start and leave operations."""

    participant_token: str = Field(min_length=32, max_length=128)


class RoomSummary(BaseModel):
    """Public room information safe to expose in the lobby."""

    id: int
    name: str
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
