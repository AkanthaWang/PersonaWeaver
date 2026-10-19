"""Logging setup kept separate from domain modules."""

import logging


def configure_logging() -> None:
    logging.getLogger("personaweaver").setLevel(logging.INFO)
