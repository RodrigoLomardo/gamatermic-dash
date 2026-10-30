import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Scope = Literal["all", "granted"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    role_ids: list[uuid.UUID] = []
    group_ids: list[uuid.UUID] = []


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    status: Literal["active", "disabled"] | None = None


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    status: str
    must_change_password: bool
    last_login_at: datetime | None
    locked_until: datetime | None
    role_ids: list[uuid.UUID] = []
    group_ids: list[uuid.UUID] = []
    temp_password: str | None = None


class IdList(BaseModel):
    ids: list[uuid.UUID]


class PermissionOut(ORM):
    code: str
    description: str | None


class RolePermIn(BaseModel):
    code: str
    scope: Scope = "all"


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = None
    permissions: list[RolePermIn] = []


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = None


class RoleOut(ORM):
    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool
    permissions: list[RolePermIn] = []


class GroupIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = None


class GroupOut(ORM):
    id: uuid.UUID
    name: str
    description: str | None
    member_ids: list[uuid.UUID] = []
    role_ids: list[uuid.UUID] = []


class GrantIn(BaseModel):
    subject_type: Literal["user", "group", "role"]
    subject_id: uuid.UUID
    access_level: Literal["view", "edit", "manage"] = "view"
    expires_at: datetime | None = None


class GrantOut(ORM):
    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    resource_type: str
    resource_id: uuid.UUID
    access_level: str
    expires_at: datetime | None


class GrantsPut(BaseModel):
    grants: list[GrantIn]


class SectorIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]{2,80}$")
    name: str = Field(min_length=2, max_length=120)


class SectorOut(ORM):
    id: uuid.UUID
    slug: str
    name: str
