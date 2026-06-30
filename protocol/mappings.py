"""
mappings.py

Lookup tables used by the mochad protocol.

This module intentionally contains NO logic.
It simply translates mochad strings into strongly typed enums.
"""

from __future__ import annotations

from models import (
	Command,
	Direction,
	Transport,
)

###############################################################################
# Direction
###############################################################################

DIRECTION_MAP = {
	"TX": Direction.TX,
	"RX": Direction.RX,
}

###############################################################################
# Transport
###############################################################################

TRANSPORT_MAP = {
	"RF": Transport.RF,
	"PL": Transport.PL,
	"RFSEC": Transport.RFSEC,
	"RFCAM": Transport.RFCAM,
}

###############################################################################
# Device / House Commands
###############################################################################

COMMAND_MAP = {
	"ON": Command.ON,
	"OFF": Command.OFF,
	"DIM": Command.DIM,
	"BRIGHT": Command.BRIGHT,
	"ALL LIGHTS ON": Command.ALL_LIGHTS_ON,
	"ALL LIGHTS OFF": Command.ALL_LIGHTS_OFF,
	"ALL UNITS OFF": Command.ALL_UNITS_OFF,
	"STATUS ON": Command.STATUS_ON,
	"STATUS OFF": Command.STATUS_OFF,
	"STATUS REQUEST": Command.STATUS_REQUEST,
	"UNKNOWN": Command.UNKNOWN,
}

ENCODE_COMMAND_MAP = {
	Command.ON: "on",
	Command.OFF: "off",
	Command.DIM: "dim",
	Command.BRIGHT: "bright",
}

RFSEC_COMMAND_MAP = {}

RFCAM_COMMAND_MAP = {}
