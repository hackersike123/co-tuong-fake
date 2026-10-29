"""Request and response schemas for account endpoints."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


class RegisterRequest(BaseModel):
    """Data required to create a player account."""

    display_name: str = Field(min_length=1, max_length=80, examples=["Red General"])
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, repr=False)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        display_name = value.strip()
        if not display_name:
            raise ValueError("Display name cannot be blank")
        return display_name


class VerifyEmailRequest(BaseModel):
    """Email and one-time code used to activate an account."""

    email: EmailStr
    otp: str = Field(pattern=r"^[0-9]{6}$", examples=["042781"])


class UserResponse(BaseModel):
    """Public account data; password hashes are never exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    email: EmailStr
    is_active: bool
    created_at: datetime
