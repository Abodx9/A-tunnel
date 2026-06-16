"""
CLI entry point for atunnel.

Usage:
    atunnel --port 8080
"""

import argparse
import os
import socket
import signal
import sys
from importlib.metadata import PackageNotFoundError, version

from atunnel import __version__
from atunnel.tunnel import Tunnel


_RESET = "\033[0m"
_BOLD = "\033[1m"
_WHITE = "\033[97m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"


def _installed_version() -> str:
    try:
        return version("atunnel")
    except PackageNotFoundError:
        return __version__


def _color(text: str, *styles: str) -> str:
    if not sys.stderr.isatty() or "NO_COLOR" in os.environ:
        return text
    return f"{''.join(styles)}{text}{_RESET}"


def _print_panel() -> None:
    lines = [
        "A-tunnel — Fast way to expose your apps to the internet",
        "               Made by Abodx",
    ]
    width = max(len(line) for line in lines) + 2
    border = _color("+" + "-" * width + "+", _CYAN)
    print(border, file=sys.stderr)
    print(
        _color("| ", _CYAN)
        + _color(lines[0].ljust(width - 2), _BOLD, _WHITE)
        + _color(" |", _CYAN),
        file=sys.stderr,
    )
    print(
        _color("| ", _CYAN)
        + _color(lines[1].ljust(width - 2), _DIM)
        + _color(" |", _CYAN),
        file=sys.stderr,
    )
    print(border, file=sys.stderr)


def _local_server_exists(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="atunnel",
        description="Expose a local port to the internet via Cloudflare Quick Tunnels.",
    )
    parser.add_argument(
        "--port", type=int, required=True, help="Local port to expose"
    )
    parser.add_argument(
        "--host", type=str, default="localhost", help="Local host (default: localhost)"
    )
    parser.add_argument(
        "--protocol",
        type=str,
        choices=["http", "https"],
        default="http",
        help="Protocol (default: http)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_installed_version()}",
    )

    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    tunnel = Tunnel(port=args.port, host=args.host, protocol=args.protocol)

    shutdown = False

    def _handle_signal(signum, frame):
        nonlocal shutdown
        if shutdown:
            sys.exit(1)
        shutdown = True
        print("\nShutting down tunnel...", file=sys.stderr)
        tunnel.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        _print_panel()
        if not _local_server_exists(args.host, args.port):
            print(
                _color(
                    f"No localhost server or app was found on {args.host}:{args.port}.",
                    _RED,
                    _BOLD,
                ),
                file=sys.stderr,
            )
            return 1

        print(
            _color(
                f"Starting tunnel for {args.protocol}://{args.host}:{args.port}...",
                _YELLOW,
            ),
            file=sys.stderr,
        )
        print(
            _color("Waiting for Cloudflare to assign a URL and verifying it's reachable...", _DIM),
            file=sys.stderr,
        )
        url = tunnel.start()

        print(_color("\n✓ Tunnel is live at:", _GREEN, _BOLD), file=sys.stderr)
        print(url)
        sys.stdout.flush()
        print(_color("Press Ctrl+C to stop.", _DIM), file=sys.stderr)

        # Block until tunnel exits or user interrupts
        import time

        while tunnel.is_running and not shutdown:
            time.sleep(1)

        if not shutdown and not tunnel.is_running:
            print("Tunnel process exited unexpectedly.", file=sys.stderr)
            return 1
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        tunnel.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
