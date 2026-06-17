"""
CLI entry point for atunnel.

Usage:
    atunnel --port 8080
    atunnel --auto
"""
from __future__ import annotations
import argparse
import os
import socket
import signal
import sys
import time
import threading
from importlib.metadata import PackageNotFoundError, version

from atunnel import __version__
from atunnel.tunnel import Tunnel


_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_ITALIC = "\033[3m"

# Foreground colours
_WHITE   = "\033[97m"
_CYAN    = "\033[96m"      # bright cyan
_BLUE    = "\033[94m"      # bright blue
_GREEN   = "\033[92m"      # bright green
_YELLOW  = "\033[93m"      # bright yellow
_RED     = "\033[91m"      # bright red
_MAGENTA = "\033[95m"      # bright magenta
_GRAY    = "\033[90m"      # dark gray

# Background colours (used for the URL highlight)
_BG_GREEN  = "\033[42m"
_BG_BLUE   = "\033[44m"


# Well-known ports for --auto detection 

_AUTO_PORTS = [
    (3000,  "Node / React / Next.js"),
    (3001,  "Node / CRA alt"),
    (4000,  "Phoenix / Gatsby"),
    (4200,  "Angular CLI"),
    (5000,  "Flask / Python"),
    (5001,  "Flask alt"),
    (5173,  "Vite"),
    (5174,  "Vite alt"),
    (6006,  "Storybook"),
    (7860,  "Gradio"),
    (8000,  "Django / Python"),
    (8001,  "Django alt"),
    (8080,  "General / Spring"),
    (8081,  "General alt"),
    (8888,  "Jupyter"),
    (9000,  "PHP / SonarQube"),
    (9090,  "Prometheus"),
    (11434, "Ollama"),
]



def _supports_color() -> bool:
    return sys.stderr.isatty() and "NO_COLOR" not in os.environ


def _c(text: str, *styles: str) -> str:
    """Apply ANSI styles only when the terminal supports them."""
    if not _supports_color():
        return text
    return f"{''.join(styles)}{text}{_RESET}"


def _installed_version() -> str:
    try:
        return version("atunnel")
    except PackageNotFoundError:
        return __version__


def _local_server_exists(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _scan_ports(host: str) -> list[tuple[int, str]]:
    """Return list of (port, label) for every open port in _AUTO_PORTS."""
    found = []
    for port, label in _AUTO_PORTS:
        if _local_server_exists(host, port, timeout=0.4):
            found.append((port, label))
    return found



_BANNER = r"""                                  
     _         _                          _ 
    / \       | |_ _   _ _ __  _ __   ___| |
   / _ \ _____| __| | | | '_ \| '_ \ / _ \ |
  / ___ \_____| |_| |_| | | | | | | |  __/ |
 /_/   \_\     \__|\__,_|_| |_|_| |_|\___|_|                                           
"""


def _print_banner() -> None:
    ver = _installed_version()
    if _supports_color():
        # Gradient-like: first two lines cyan, last three blue
        lines = _BANNER.splitlines()
        coloured = []
        colours = [_CYAN, _CYAN, _BLUE, _BLUE, _BLUE]
        for i, line in enumerate(lines):
            col = colours[i] if i < len(colours) else _CYAN
            coloured.append(_c(line, col, _BOLD))
        print("\n".join(coloured), file=sys.stderr)
    else:
        print(_BANNER, file=sys.stderr)

    # Tagline row
    tag  = _c("  Fast localhost → internet tunnels via Cloudflare  ", _DIM, _ITALIC)
    ver_badge = _c(f" v{ver} ", _BOLD, _CYAN)
    by   = _c("  by Abodx9", _GRAY)
    print(f"{tag}{ver_badge}{by}", file=sys.stderr)
    print(_c("  " + "─" * 52, _GRAY), file=sys.stderr)
    print(file=sys.stderr)


def _print_table(rows: list[tuple[int, str]], selected: int | None = None) -> None:
    """Print a styled table of discovered ports."""
    col_w = [6, 8, 30]  # Port | Status | App
    hdr   = ["PORT", "STATUS", "APP / FRAMEWORK"]
    sep   = _c("  ├" + "─" * (col_w[0]+2) + "┼" + "─" * (col_w[1]+2) + "┼" + "─" * (col_w[2]+2) + "┤", _GRAY)
    top   = _c("  ┌" + "─" * (col_w[0]+2) + "┬" + "─" * (col_w[1]+2) + "┬" + "─" * (col_w[2]+2) + "┐", _GRAY)
    bot   = _c("  └" + "─" * (col_w[0]+2) + "┴" + "─" * (col_w[1]+2) + "┴" + "─" * (col_w[2]+2) + "┘", _GRAY)

    def _row(p: str, s: str, a: str, pc=_WHITE, sc=_WHITE, ac=_WHITE) -> str:
        pipe = _c(" │ ", _GRAY)
        return (
            _c("  │ ", _GRAY)
            + _c(p.ljust(col_w[0]), pc, _BOLD)
            + pipe
            + _c(s.ljust(col_w[1]), sc)
            + pipe
            + _c(a.ljust(col_w[2]), ac)
            + _c(" │", _GRAY)
        )

    print(top, file=sys.stderr)
    print(_row(hdr[0], hdr[1], hdr[2], _CYAN, _CYAN, _CYAN), file=sys.stderr)

    for port, label in rows:
        print(sep, file=sys.stderr)
        is_sel = port == selected
        star = " ★" if is_sel else "  "
        port_str = f"{port}{star}"
        status_str = "● OPEN"
        p_col  = _YELLOW if is_sel else _GREEN
        s_col  = _GREEN
        a_col  = _WHITE if not is_sel else _YELLOW
        print(_row(port_str, status_str, label, p_col, s_col, a_col), file=sys.stderr)

    print(bot, file=sys.stderr)


def _print_status_box(port: int, protocol: str, host: str, url: str | None = None) -> None:
    """Print a summary status box once the tunnel is live."""
    print(file=sys.stderr)
    print(_c("  Local  → ", _DIM) + _c(f"{protocol}://{host}:{port}", _CYAN, _BOLD), file=sys.stderr)
    if url:
        print(_c("  Public → ", _DIM) + _c(url, _GREEN, _BOLD), file=sys.stderr)
    print(file=sys.stderr)


class _Spinner:
    """A simple terminal spinner that runs in a background thread."""

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str) -> None:
        self._msg     = message
        self._stop    = threading.Event()
        self._thread  = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = self._FRAMES[i % len(self._FRAMES)]
            line  = _c(f"  {frame} ", _CYAN) + _c(self._msg, _DIM)
            sys.stderr.write(f"\r{line}  ")
            sys.stderr.flush()
            time.sleep(0.08)
            i += 1

    def start(self) -> "_Spinner":
        if _supports_color():
            self._thread.start()
        else:
            sys.stderr.write(f"  {self._msg}\n")
            sys.stderr.flush()
        return self

    def stop(self, final_line: str = "") -> None:
        self._stop.set()
        if _supports_color() and self._thread.is_alive():
            self._thread.join(timeout=1)
            sys.stderr.write("\r\033[K")  # clear entire spinner line
            sys.stderr.flush()
        if final_line:
            print(final_line, file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="atunnel",
        description="Expose a local port to the internet via Cloudflare Quick Tunnels.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    port_group = parser.add_mutually_exclusive_group(required=True)
    port_group.add_argument(
        "--port", "-p",
        type=int,
        help="Local port to expose (e.g. --port 8080)",
    )
    port_group.add_argument(
        "--auto", "-a",
        action="store_true",
        help=(
            "Auto-detect an open local port from a list of well-known\n"
            "dev-server ports and tunnel the first one found."
        ),
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Local host to tunnel (default: localhost)",
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

    _print_banner()

    #  Resolve port 

    if args.auto:
        spinner = _Spinner("Scanning local ports for running servers…").start()
        time.sleep(0.3)  # let spinner render at least one frame
        open_ports = _scan_ports(args.host)
        spinner.stop()

        if not open_ports:
            print(
                _c("\n  ✗ No running dev server detected on any well-known port.", _RED, _BOLD),
                file=sys.stderr,
            )
            print(
                _c(
                    "  Tip: start your app first, then run  atunnel --auto\n"
                    "       or specify a port manually:      atunnel --port <PORT>",
                    _GRAY,
                ),
                file=sys.stderr,
            )
            return 1

        selected_port = open_ports[0][0]

        print(
            _c(f"\n  Found {len(open_ports)} open port(s):\n", _CYAN, _BOLD),
            file=sys.stderr,
        )
        _print_table(open_ports, selected=selected_port)
        print(
            _c(f"\n  ★  Auto-selected port {selected_port} — tunnelling it now.\n", _YELLOW, _BOLD),
            file=sys.stderr,
        )

        port = selected_port

    else:
        port = args.port
        if not 1 <= port <= 65535:
            parser.error("--port must be between 1 and 65535")

        if not _local_server_exists(args.host, port):
            print(
                _c(f"\n  ✗ No server found on {args.host}:{port}.\n"
                   f"    Make sure your app is running, then try again.", _RED, _BOLD),
                file=sys.stderr,
            )
            return 1

    #  Start tunnel 

    tunnel  = Tunnel(port=port, host=args.host, protocol=args.protocol)
    shutdown = False

    def _handle_signal(signum, frame):
        nonlocal shutdown
        if shutdown:
            sys.exit(1)
        shutdown = True
        print(_c("\n\n  Shutting down tunnel…", _YELLOW), file=sys.stderr)
        tunnel.stop()

    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    spinner = _Spinner(
        "Connecting to Cloudflare and verifying tunnel is reachable…"
    ).start()

    try:
        url = tunnel.start()
    except RuntimeError as e:
        spinner.stop()
        print(_c(f"\n  ✗ Error: {e}", _RED, _BOLD), file=sys.stderr)
        return 1

    spinner.stop()

    # Print the live status box
    print(file=sys.stderr)
    _print_status_box(port, args.protocol, args.host, url)
    print(
        _c("\n  ✓ Tunnel is live! Copy the public URL above.", _GREEN, _BOLD),
        file=sys.stderr,
    )
    print(_c("  Press Ctrl+C to stop.\n", _DIM), file=sys.stderr)

    # Emit the URL to stdout if not in a tty (for machine readability)
    if not sys.stdout.isatty():
        print(url)
        sys.stdout.flush()

    #  Keep alive until Ctrl+C

    while tunnel.is_running and not shutdown:
        time.sleep(1)

    if not shutdown and not tunnel.is_running:
        print(_c("  ✗ Tunnel process exited unexpectedly.", _RED), file=sys.stderr)
        return 1

    tunnel.stop()
    print(_c("\n  Tschau! \n", _CYAN), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
