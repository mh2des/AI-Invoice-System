from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    invite_code: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool

    model_config = {"from_attributes": True}
