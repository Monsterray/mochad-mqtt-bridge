"""
version.py

Generated bridge version information. Regenerate with
scripts/release/sync-version-files.sh.
"""

BRIDGE_NAME = "mqtt-mochad-bridge"

BRIDGE_VERSION = "0.4.0"

BRIDGE_AUTHOR = "Open Source"

SUPPORTED_MOCHAD = "0.1.18"

# The compatibility workflow verifies every supported minor from this floor
# through the latest version currently listed in its test matrix.
SUPPORTED_PYTHON = (3, 10)
