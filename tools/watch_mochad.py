#!/usr/bin/env python3
"""
Watch raw mochad TCP output from inside the bridge image.
"""

from __future__ import annotations

import argparse
import socket
import sys
from datetime import datetime


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="mochad")
    parser.add_argument("--port", type=int, default=1099)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--status",
        action="store_true",
        help="send an initial st request after connecting",
    )
    args = parser.parse_args()

    print(f"Connecting to mochad at {args.host}:{args.port}...")

    try:
        with socket.create_connection(
            (args.host, args.port),
            timeout=args.timeout,
        ) as sock:
            print("Connected. Press X10 remote buttons now. Ctrl-C to stop.")

            if args.status:
                sock.sendall(b"st\n")
                print("Sent st status request.")

            sock.settimeout(None)
            buffer = ""

            while True:
                data = sock.recv(4096)

                if not data:
                    print("mochad closed the connection.")
                    return 1

                buffer += data.decode("utf-8", errors="replace")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.rstrip("\r")
                    timestamp = datetime.now().isoformat(timespec="seconds")
                    print(f"{timestamp} {line}", flush=True)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except OSError as exc:
        print(
            f"FAIL could not read from {args.host}:{args.port}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
