import uuid

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(max_length=256)


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    must_change_password: bool
    roles: list[str]
    permissions: dict[str, str]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: MeOut
