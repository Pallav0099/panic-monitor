from __future__ import annotations

import os
import secrets
from pathlib import Path

from loguru import logger

SECRET_KEY_LENGTH = 32


def load_or_create_secret_key(path: Path) -> bytes:
    """Load a 32-byte ed25519 secret key from *path*, or generate and save a new one."""
    if path.exists():
        return _load_secret_key(path)

    key = _generate_secret_key()
    _save_secret_key(path, key)
    return key


def _generate_secret_key() -> bytes:
    return secrets.token_bytes(SECRET_KEY_LENGTH)


def _save_secret_key(path: Path, key: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    os.chmod(path, 0o600)
    logger.info("Generated new secret key → {}", path)


def _load_secret_key(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) != SECRET_KEY_LENGTH:
        raise ValueError(
            f"Invalid secret key at {path}: {len(data)} bytes (expected {SECRET_KEY_LENGTH})"
        )

    mode = oct(path.stat().st_mode & 0o777)
    if mode != "0o600":
        logger.warning("secret.key permissions are {} — expected 0o600", mode)

    logger.debug("Loaded secret key from {}", path)
    return data
