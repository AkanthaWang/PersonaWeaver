from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=8, max_length=128)
    email: str = Field(default="", max_length=254)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("用户名至少 2 个字符")
        return value


class Profile(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    email: str = Field(default="", max_length=254)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value):
        return Credentials.clean_username(value)


class RoleSettings(BaseModel):
    prompt: str = Field(default="", max_length=12000)
    avatar: Optional[str] = Field(default=None, max_length=500)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    password: str = Field(min_length=8, max_length=128)


__all__ = ["Credentials", "PasswordChange", "Profile", "RoleSettings"]
