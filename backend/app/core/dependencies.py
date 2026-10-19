"""FastAPI dependencies shared by the domain routers."""

from typing import Optional

from fastapi import Header, Request

from .security import resolve_user


def get_db(request: Request):
    return request.app.state.db


def get_config(request: Request):
    return request.app.state.config


def current_user(request: Request, authorization: Optional[str] = Header(default=None)):
    return resolve_user(get_db(request), authorization)
