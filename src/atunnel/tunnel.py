"""
Starts a cloudflared quick tunnel subprocess and parses the public URL.
"""

import re
import os
import subprocess
import threading
import time
from typing import Optional

from atunnel.binary import ensure_binary


_URL_PATTERN = re.compile(
    r"https://(?!api\.)[a-zA-Z0-9-]+\.trycloudflare\.com\b"
)

# Seconds to wait after URL is found before returning it. Do not actively probe
# DNS here: on Windows, an early NXDOMAIN can be cached and make a fresh
# trycloudflare hostname look broken even after Cloudflare publishes it.
_URL_PROPAGATION_DELAY = 5.0


class Tunnel:
    """Manages a cloudflared quick tunnel subprocess."""

    def __init__(self, port: int, host: str = "localhost", protocol: str = "http") -> None:
        self.port = port
        self.host = host
        self.protocol = protocol
        self._process: Optional[subprocess.Popen] = None
        self._public_url: Optional[str] = None
        self._output_lines: list = []
        self._lock = threading.Lock()
        # Event set as soon as any thread finds the URL in output
        self._url_found_event = threading.Event()
        self._found_url: Optional[str] = None

    @property
    def public_url(self) -> Optional[str]:
        return self._public_url

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, timeout: float = 30.0) -> str:
        """Start the tunnel and return the public URL."""
        binary = ensure_binary()
        local_url = f"{self.protocol}://{self.host}:{self.port}"
        cmd = [
            str(binary),
            "tunnel",
            "--url", local_url,
            "--no-autoupdate",
            "--http-host-header", "localhost",
        ]

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            env={**os.environ, "NO_AUTOUPDATE": "true"},
        )

        # Read both stdout and stderr — different cloudflared versions use different streams
        stderr_reader = threading.Thread(
            target=self._read_stream, args=(self._process.stderr,), daemon=True
        )
        stdout_reader = threading.Thread(
            target=self._read_stream, args=(self._process.stdout,), daemon=True
        )
        stderr_reader.start()
        stdout_reader.start()

        url = self._wait_for_url(timeout)
        if url is None:
            self.stop()
            with self._lock:
                output = "\n".join(self._output_lines[-20:])
            raise RuntimeError(
                f"Failed to get tunnel URL within {timeout}s.\nOutput:\n{output}"
            )

        self._public_url = url
        return url

    def stop(self) -> None:
        """Stop the tunnel process."""
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=3)
        self._process = None
        self._public_url = None

    def _read_stream(self, stream) -> None:
        """Read a stream, storing log lines and scanning raw chunks for the URL."""
        if stream is None:
            return
        pending_line = ""
        search_buffer = ""

        def store_line(line: str) -> None:
            line = line.strip()
            if not line:
                return
            with self._lock:
                self._output_lines.append(line)

        try:
            while True:
                chunk = stream.read(1024)
                if not chunk:
                    break

                if isinstance(chunk, bytes):
                    text = chunk.decode("utf-8", errors="replace")
                else:
                    text = chunk

                # Match against chunks instead of only completed lines. Some
                # cloudflared output can arrive without a newline before the
                # startup timeout, while Node's OpenTunnel sees it as a data
                # event immediately.
                search_buffer = (search_buffer + text)[-2048:]
                if not self._url_found_event.is_set():
                    match = _URL_PATTERN.search(search_buffer)
                    if match:
                        self._found_url = match.group(0)
                        self._url_found_event.set()

                pending_line += text
                lines = pending_line.splitlines(keepends=True)
                if lines and not lines[-1].endswith(("\n", "\r")):
                    pending_line = lines.pop()
                else:
                    pending_line = ""
                for line in lines:
                    store_line(line)

            store_line(pending_line)
        except (ValueError, OSError):
            pass

    def _wait_for_url(self, timeout: float) -> Optional[str]:
        """
        Wait until cloudflared emits a public URL, then give Cloudflare a brief
        moment to publish the quick-tunnel hostname before returning it.
        """
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if self._url_found_event.wait(timeout=0.1):
                break
            if not self.is_running:
                return None
        else:
            return None

        url = self._found_url
        if url is None:
            return None

        # Give Cloudflare's edge a moment to propagate the tunnel.
        delay_deadline = time.monotonic() + _URL_PROPAGATION_DELAY
        while time.monotonic() < delay_deadline:
            if not self.is_running:
                return None
            time.sleep(0.1)

        return url

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()
