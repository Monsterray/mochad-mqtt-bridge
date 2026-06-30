"""
validation.py

Validation and normalization helpers for the mochad protocol.
"""

from __future__ import annotations

import re

###############################################################################
# Constants
###############################################################################

HOUSE_CODES = tuple("ABCDEFGHIJKLMNOP")

MIN_UNIT = 1

MAX_UNIT = 16

ADDRESS_RE = re.compile(
	r"^(?P<house>[A-Pa-p])(?P<unit>(?:[1-9]|1[0-6]))$"
)

HOUSE_RE = re.compile(
	r"^[A-Pa-p]$"
)

###############################################################################
# Address Helpers
###############################################################################


def normalize_house(
	house: str,
) -> str:
	"""
	Normalize a house code.

	Example:
	    a -> A
	"""

	house = house.strip().upper()

	if not HOUSE_RE.fullmatch(house):
		raise ValueError(
			f"Invalid house code '{house}'."
		)

	return house


def normalize_address(
	address: str,
) -> str:
	"""
	Normalize an X10 address.

	Examples

	    a1

	    A01

	    a01

	become

	    A1
	"""

	address = address.strip().upper()

	match = ADDRESS_RE.fullmatch(address)

	if match is None:
		raise ValueError(
			f"Invalid X10 address '{address}'."
		)

	house = match.group("house")

	unit = int(match.group("unit"))

	return f"{house}{unit}"


###############################################################################
# Validation
###############################################################################


def is_valid_house(
	house: str,
) -> bool:

	try:
		normalize_house(house)
		return True

	except ValueError:
		return False


def is_valid_address(
	address: str,
) -> bool:

	try:
		normalize_address(address)
		return True

	except ValueError:
		return False


###############################################################################
# Split / Join Helpers
###############################################################################


def split_address(
	address: str,
) -> tuple[str, int]:
	"""
	A5 -> ("A", 5)
	"""

	address = normalize_address(address)

	return (
		address[0],
		int(address[1:]),
	)


def join_address(
	house: str,
	unit: int,
) -> str:
	"""
	("A", 5) -> A5
	"""

	house = normalize_house(house)

	if unit < MIN_UNIT or unit > MAX_UNIT:
		raise ValueError(
			f"Invalid unit '{unit}'."
		)

	return f"{house}{unit}"


###############################################################################
# Misc Helpers
###############################################################################


def normalize_token(
	value: str,
) -> str:
	"""
	Normalize mochad command strings.

	Examples

	    "  All   Lights   On "

	becomes

	    "ALL LIGHTS ON"
	"""

	return " ".join(
		value.strip().upper().split()
	)
