"""
Starts a cloudflared quick tunnel subprocess and parses the public URL.
"""

import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from atunnel.binary import ensure_binary


_URL_PATTERN = re.compile(
    r"https://[-a-zA-Z0-9@:%._\+~#=]{1,256}\.trycloudflare\.com"
)


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
        cmd = [str(binary), "tunnel", "--url", local_url, "--no-autoupdate"]

        self._process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
        )

        reader = threading.Thread(target=self._read_stderr, daemon=True)
        reader.start()

        url = self._wait_for_url(timeout)
        if url is None:
            self.stop()
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

    def _read_stderr(self) -> None:
        proc = self._process
        if proc is None or proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                line = line.strip()
                if line:
                    with self._lock:
                        self._output_lines.append(line)
        except (ValueError, OSError):
            pass

    def _wait_for_url(self, timeout: float) -> Optional[str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process and self._process.poll() is not None:
                return None
            with self._lock:
                for line in self._output_lines:
                    match = _URL_PATTERN.search(line)
                    if match:
                        return match.group(0)
            time.sleep(0.2)
        return None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()