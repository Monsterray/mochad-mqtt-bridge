"""
Command encoding for the mochad protocol.
"""

from __future__ import annotations

from models import Command

from .mappings import ENCODE_COMMAND_MAP
from .validation import normalize_address


def encode_command(
    transport: str,
    address: str,
    command: Command,
) -> str:
    transport = transport.strip().lower()

    if transport not in {"rf", "pl"}:
        raise ValueError(
            f"Unsupported mochad transport '{transport}'."
        )

    address = normalize_address(address)

    try:
        suffix = ENCODE_COMMAND_MAP[command]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported mochad command {command}."
        ) from exc

    return f"{transport} {address} {suffix}"


def encode_rf_command(
    address: str,
    command: Command,
) -> str:
    return encode_command("rf", address, command)


def encode_pl_command(
    address: str,
    command: Command,
) -> str:
    return encode_command("pl", address, command)
