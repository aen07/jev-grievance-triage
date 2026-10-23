"""Load secrets from a local .env file (gitignored). Real environment variables always win."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env() -> None:
    load_dotenv(ENV_FILE, override=False)
