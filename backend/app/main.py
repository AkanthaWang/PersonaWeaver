"""Canonical FastAPI application entry point."""

from .application import create_app

app = create_app()

__all__ = ["app", "create_app"]
