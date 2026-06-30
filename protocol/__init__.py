"""
Public protocol API.

The protocol package owns all mochad text parsing, command encoding,
normalization, and protocol-specific lookup tables.
"""

from .encoder import encode_command, encode_pl_command, encode_rf_command
from .parser import ProtocolCapabilities, ProtocolParser
from .validation import is_valid_address, normalize_address, normalize_house

__all__ = [
    "ProtocolCapabilities",
    "ProtocolParser",
    "encode_command",
    "encode_rf_command",
    "encode_pl_command",
    "normalize_address",
    "normalize_house",
    "is_valid_address",
]
