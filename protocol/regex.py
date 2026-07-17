"""
Compiled regular expressions for the mochad protocol.

Regexes should NEVER be compiled anywhere else.
"""

from __future__ import annotations

import re

###############################################################################
# Common
###############################################################################

TIMESTAMP = (
    r"\d\d/\d\d\s+\d\d:\d\d:\d\d"
)

ADDRESS = (
    r"[A-P](?:[1-9]|1[0-6])"
)

HOUSE = (
    r"[A-P]"
)

###############################################################################
# Device Events
###############################################################################

DEVICE_EVENT_RE = re.compile(
    rf"""
    ^
    {TIMESTAMP}
    \s+
    (?P<direction>Tx|Rx)
    \s+
    (?P<transport>RF|PL)
    \s+
    HouseUnit:
    \s+
    (?P<address>{ADDRESS})
    \s+
    Func:
    \s+
    (?P<command>.+?)
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

###############################################################################
# House Events
###############################################################################

HOUSE_EVENT_RE = re.compile(
    rf"""
    ^
    {TIMESTAMP}
    \s+
    (?P<direction>Tx|Rx)
    \s+
    (?P<transport>RF|PL)
    \s+
    House:
    \s+
    (?P<house>{HOUSE})
    \s+
    Func:
    \s+
    (?P<command>.+?)
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

###############################################################################
# Status
###############################################################################

DEVICE_SELECTED_RE = re.compile(
    rf"^{TIMESTAMP}\s+Device selected$",
    re.IGNORECASE,
)

DEVICE_STATUS_RE = re.compile(
    rf"^{TIMESTAMP}\s+Device status$",
    re.IGNORECASE,
)

SECURITY_STATUS_RE = re.compile(
    rf"^{TIMESTAMP}\s+Security sensor status$",
    re.IGNORECASE,
)

END_STATUS_RE = re.compile(
    rf"^{TIMESTAMP}\s+End status$",
    re.IGNORECASE,
)

HOUSE_COUNT_RE = re.compile(
    rf"""
    ^
    {TIMESTAMP}
    \s+
    House
    \s+
    (?P<house>[A-P])
    :
    \s+
    (?P<count>\d+)
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

HOUSE_STATUS_RE = re.compile(
    rf"""
    ^
    {TIMESTAMP}
    \s+
    House
    \s+
    (?P<house>[A-P])
    :
    \s+
    (?P<devices>.+)
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

STRICT_HOUSE_STATUS_RE = re.compile(
    rf"""
    ^
    {TIMESTAMP}
    \s+
    House
    \s+
    (?P<house>[A-P])
    :
    \s+
    (?P<devices>
        (?:[1-9]|1[0-6])
        \s*=\s*
        [01]
        (?:
            \s*,\s*
            (?:[1-9]|1[0-6])
            \s*=\s*
            [01]
        )*
    )
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

###############################################################################
# Security
###############################################################################

RFSEC_RE = re.compile(
    rf"""
    ^
    {TIMESTAMP}
    \s+
    (?P<direction>Tx|Rx)
    \s+
    RFSEC
    \s+
    Addr:
    \s+
    (?P<address>[0-9A-F:]+)
    \s+
    Func:
    \s+
    (?P<command>.+)
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

###############################################################################
# Cameras
###############################################################################

RFCAM_RE = re.compile(
    rf"""
    ^
    {TIMESTAMP}
    \s+
    (?P<direction>Tx|Rx)
    \s+
    RFCAM
    \s+
    (?P<house>[A-P])
    \s+
    (?P<command>[A-Z0-9_]+)
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)
