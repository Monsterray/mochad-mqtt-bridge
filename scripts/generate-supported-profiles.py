#!/usr/bin/env python3
"""Generate the supported-profile document from the validated registry."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from device_registry import generated_supported_profiles_markdown


OUTPUT = ROOT / "docs" / "supported-profiles.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the committed document differs from generated output",
    )
    args = parser.parse_args()
    generated = generated_supported_profiles_markdown()

    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != generated:
            print(f"{OUTPUT} is out of date", file=sys.stderr)
            return 1
        return 0

    OUTPUT.write_text(generated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
