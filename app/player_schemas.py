from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlayerStatsResponse(BaseModel):
    user_id: int
    display_name: str
    username: str | None
    elo: int
    games_played: int
    wins: int
    draws: int
    losses: int
    win_rate: float
    rank: int | None


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    username: str | None
    display_name: str
    elo: int
    games_played: int
    wins: int
    draws: int
    losses: int
    win_rate: float


class CommunityMatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_key: str
    room_id: int
    room_name: str
    red_player: str
    black_player: str
    red_user_id: int | None
    black_user_id: int | None
    result: str
    reason: str | None
    winner: str | None
    notation: str
    final_fen: str
    finished_at: datetime
    red_elo_change: int
    black_elo_change: int


class CommunitySummaryResponse(BaseModel):
    registered_players: int
    open_public_rooms: int
    completed_public_games: int
