"""Multiplex account, room, and PvE commands over one native WebSocket."""

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from starlette.concurrency import run_in_threadpool

from .. import database
from ..schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
    VerifyEmailRequest,
)
from ..room_schemas import (
    RoomActionRequest,
    RoomCodeJoinRequest,
    RoomCreateRequest,
    RoomInviteRequest,
    RoomJoinRequest,
    RoomReadyRequest,
)
from ..pve_schemas import PveAiMoveRequest, PveGameStartRequest, PvePlayerMoveRequest
from ..models import User
from . import auth as auth_routes
from . import pve as pve_routes
from . import rooms as room_routes


logger = logging.getLogger(__name__)
router = APIRouter()


@dataclass
class DispatchResult:
    data: Any
    background_tasks: BackgroundTasks | None = None


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _request_for_socket_login() -> Any:
    """Build the empty HTTP request expected by the shared login service."""
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 0),
            "server": ("localhost", 443),
        }
    )


def _dispatch(event: str, data: dict[str, Any]) -> DispatchResult:
    """Call existing domain services while keeping the public transport on WS."""
    if event == "system.ping":
        return DispatchResult({"pong": True})

    if event in {
        "auth.register",
        "auth.verify_email",
        "auth.login",
        "auth.forgot_password",
        "auth.reset_password",
        "auth.resend_verification",
    }:
        with database.SessionLocal() as session:
            if event == "auth.register":
                request = RegisterRequest.model_validate(data)
                user = auth_routes.register_account(request, session)
                return DispatchResult(UserResponse.model_validate(user))
            if event == "auth.verify_email":
                request = VerifyEmailRequest.model_validate(data)
                user = auth_routes.verify_account_email(request, session)
                return DispatchResult(UserResponse.model_validate(user))
            if event == "auth.login":
                # WebSocket responses cannot set the HttpOnly refresh cookie used
                # by the legacy HTTP route. Keep this socket login access-token-only.
                request = LoginRequest.model_validate(data).model_copy(
                    update={"remember_me": False}
                )
                response = auth_routes.Response()
                token = auth_routes.login(
                    request,
                    _request_for_socket_login(),
                    response,
                    session,
                )
                identifier = request.identifier.lower()
                user = session.scalar(
                    select(User).where(
                        or_(
                            func.lower(User.email) == identifier,
                            func.lower(User.username) == identifier,
                        )
                    )
                )
                return DispatchResult(
                    {
                        **token.model_dump(mode="json"),
                        "user": UserResponse.model_validate(user).model_dump(mode="json"),
                    }
                )
            if event == "auth.forgot_password":
                request = ForgotPasswordRequest.model_validate(data)
                return DispatchResult(auth_routes.forgot_password(request, session))
            if event == "auth.resend_verification":
                request = ForgotPasswordRequest.model_validate(data)
                email = str(request.email).strip().lower()
                user = session.scalar(select(User).where(User.email == email))
                if user is None or user.is_active:
                    raise HTTPException(status_code=404, detail="Pending account not found")
                try:
                    auth_routes.ensure_email_configured()
                    auth_routes.clear_email_otp(session, user.id)
                    otp = auth_routes.issue_email_otp(session, user.id)
                    session.commit()
                    auth_routes.send_verification_email(email, otp)
                except auth_routes.EmailConfigurationError as exc:
                    session.rollback()
                    raise HTTPException(status_code=503, detail="Email service is not configured") from exc
                except auth_routes.EmailDeliveryError as exc:
                    session.rollback()
                    auth_routes.clear_email_otp(session, user.id)
                    session.commit()
                    raise HTTPException(status_code=503, detail="Could not send verification email") from exc
                return DispatchResult({"message": "Verification code sent"})
            request = ResetPasswordRequest.model_validate(data)
            return DispatchResult(auth_routes.reset_password(request, session))

    if event == "room.list":
        return DispatchResult(room_routes.get_public_rooms())
    if event == "room.create":
        tasks = BackgroundTasks()
        result = room_routes.create_public_room(
            RoomCreateRequest.model_validate(data), tasks
        )
        return DispatchResult(result, tasks)
    if event == "room.join_code":
        tasks = BackgroundTasks()
        result = room_routes.join_room_by_code(
            RoomCodeJoinRequest.model_validate(data), tasks
        )
        return DispatchResult(result, tasks)

    room_id_value = data.get("room_id")
    if event.startswith("room.") and event != "room.list":
        if isinstance(room_id_value, bool):
            raise HTTPException(status_code=422, detail="room_id must be a positive integer")
        try:
            room_id = int(room_id_value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail="room_id must be a positive integer"
            ) from exc
        if room_id <= 0:
            raise HTTPException(status_code=422, detail="room_id must be a positive integer")

        if event == "room.join":
            tasks = BackgroundTasks()
            result = room_routes.join_public_room(
                room_id,
                RoomJoinRequest.model_validate(data),
                tasks,
            )
            return DispatchResult(result, tasks)
        if event == "room.read":
            result = room_routes.get_room_details(
                room_id,
                participant_token=data.get("participant_token"),
                invite_token=data.get("invite_token"),
                password=data.get("password"),
            )
            return DispatchResult(result)
        if event == "room.game":
            result = room_routes.get_room_game_state(
                room_id,
                participant_token=data.get("participant_token"),
                invite_token=data.get("invite_token"),
                password=data.get("password"),
            )
            return DispatchResult(result)
        if event == "room.history":
            result = room_routes.get_room_match_history(
                room_id,
                participant_token=data.get("participant_token"),
                invite_token=data.get("invite_token"),
                password=data.get("password"),
                room_uuid=data.get("room_uuid"),
            )
            return DispatchResult(result)
        if event == "room.ready":
            tasks = BackgroundTasks()
            result = room_routes.ready_room_player(
                room_id,
                RoomReadyRequest.model_validate(data),
                tasks,
            )
            return DispatchResult(result, tasks)
        if event == "room.start":
            tasks = BackgroundTasks()
            result = room_routes.start_public_room(
                room_id,
                RoomActionRequest.model_validate(data),
                tasks,
            )
            return DispatchResult(result, tasks)
        if event == "room.leave":
            tasks = BackgroundTasks()
            result = room_routes.leave_public_room(
                room_id,
                RoomActionRequest.model_validate(data),
                tasks,
            )
            return DispatchResult(result, tasks)
        if event == "room.invite":
            result = room_routes.email_room_invitation(
                room_id,
                RoomInviteRequest.model_validate(data),
            )
            return DispatchResult(result)

    if event == "pve.options":
        return DispatchResult(pve_routes.get_pve_options())
    if event == "pve.start":
        return DispatchResult(
            pve_routes.start_pve_game(PveGameStartRequest.model_validate(data))
        )
    if event == "pve.player_move":
        return DispatchResult(
            pve_routes.validate_pve_player_move(PvePlayerMoveRequest.model_validate(data))
        )
    if event == "pve.ai_move":
        return DispatchResult(
            pve_routes.request_ai_move(PveAiMoveRequest.model_validate(data))
        )

    raise HTTPException(status_code=404, detail="Unsupported WebSocket event")


@router.websocket("/ws")
async def api_socket(websocket: WebSocket) -> None:
    """Handle one request per event and correlate replies by the caller's id.

    Request: ``{"id":"...","event":"room.list","data":{}}``
    Response: ``{"id":"...","event":"room.list.result","ok":true,"data":...}``
    """
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await websocket.send_json(
                    {"id": None, "event": "error", "ok": False, "error": {"status": 422, "detail": "Expected an object"}}
                )
                continue

            request_id = message.get("id")
            event = message.get("event")
            data = message.get("data", {})
            if not isinstance(event, str) or not event or not isinstance(data, dict):
                await websocket.send_json(
                    {"id": request_id, "event": "error", "ok": False, "error": {"status": 422, "detail": "event and object data are required"}}
                )
                continue

            try:
                result = await run_in_threadpool(_dispatch, event, data)
                if result.background_tasks is not None:
                    await result.background_tasks()
                response = {
                    "id": request_id,
                    "event": f"{event}.result",
                    "ok": True,
                    "data": _json_value(result.data),
                }
            except HTTPException as exc:
                response = {
                    "id": request_id,
                    "event": f"{event}.result",
                    "ok": False,
                    "error": {"status": exc.status_code, "detail": exc.detail},
                }
            except ValidationError as exc:
                response = {
                    "id": request_id,
                    "event": f"{event}.result",
                    "ok": False,
                    "error": {
                        "status": 422,
                        "detail": exc.errors(include_url=False, include_input=False),
                    },
                }
            except Exception:
                logger.exception(
                    "WebSocket command failed",
                    extra={"event": "websocket.command_failed", "command": event},
                )
                response = {
                    "id": request_id,
                    "event": f"{event}.result",
                    "ok": False,
                    "error": {"status": 500, "detail": "Internal server error"},
                }
            await websocket.send_json(response)
    except WebSocketDisconnect:
        return
