import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PairStartOut(BaseModel):
    device_code: str
    user_code: str
    expires_in: int
    interval: int
    verification_path: str


class PollIn(BaseModel):
    device_code: str


class PollOut(BaseModel):
    status: Literal["authorization_pending", "slow_down", "expired", "denied", "approved"]
    interval: int | None = None
    device_id: uuid.UUID | None = None


class LookupOut(BaseModel):
    user_code: str
    requested_ip: str | None
    user_agent: str | None
    created_at: datetime
    expires_in: int


class ApproveIn(BaseModel):
    user_code: str
    name: str = Field(min_length=2, max_length=120)
    location: str | None = Field(default=None, max_length=160)
    playlist_id: uuid.UUID | None = None


class DenyIn(BaseModel):
    user_code: str


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    location: str | None
    status: str
    playlist_id: uuid.UUID | None
    last_seen_at: datetime | None
    last_ip: str | None
    user_agent: str | None
    app_version: str | None
    stale_state: str | None
    paired_at: datetime | None
    revoked_at: datetime | None
    online: bool = False


class DevicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    location: str | None = None


class DevicePlaylistIn(BaseModel):
    playlist_id: uuid.UUID | None


class DeviceTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class PlaylistItemIn(BaseModel):
    dashboard_id: uuid.UUID
    duration_seconds: int = Field(default=30, ge=5, le=3600)
    transition: Literal["fade", "slide", "none"] = "fade"


class PlaylistItemOut(PlaylistItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    position: int
    dashboard_name: str | None = None


class PlaylistIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class PlaylistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    version: int
    items: list[PlaylistItemOut] = []
    device_count: int = 0
