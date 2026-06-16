"""
Starts a cloudflared quick tunnel subprocess and parses the public URL.
"""

import re
import subprocess
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from atunnel.binary import ensure_binary


_URL_PATTERN = re.compile(
    r"https://[-a-zA-Z0-9@:%._\+~#=]{1,256}\.trycloudflare\.com"
)

# Seconds to wait after URL is found before returning it, giving Cloudflare's
# edge time to actually route traffic to the tunnel.
_URL_PROPAGATION_DELAY = 2.0

# How long to wait between reachability probe attempts.
_REACHABILITY_PROBE_INTERVAL = 1.0

# How many times to probe reachability before giving up and returning URL anyway.
_REACHABILITY_MAX_PROBES = 10


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
        cmd = [str(binary), "tunnel", "--url", local_url, "--no-autoupdate"]

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
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
        """Read lines from a stream (stdout or stderr), storing them and scanning for URL."""
        if stream is None:
            return
        try:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                with self._lock:
                    self._output_lines.append(line)
                # Check this line for the URL — no need to re-scan all lines
                if not self._url_found_event.is_set():
                    match = _URL_PATTERN.search(line)
                    if match:
                        self._found_url = match.group(0)
                        self._url_found_event.set()
        except (ValueError, OSError):
            pass

    def _wait_for_url(self, timeout: float) -> Optional[str]:
        """
        Wait until cloudflared emits a public URL, then verify it is reachable
        before returning it. This avoids handing back a URL that Cloudflare's
        edge hasn't finished routing yet.
        """
        deadline = time.monotonic() + timeout

        # Wait for the URL to appear in output
        remaining = deadline - time.monotonic()
        url_appeared = self._url_found_event.wait(timeout=max(remaining, 0))

        if not url_appeared:
            return None

        url = self._found_url
        if url is None:
            return None

        # Give Cloudflare's edge a moment to propagate the tunnel before probing
        time.sleep(_URL_PROPAGATION_DELAY)

        # Probe the URL to confirm it is actually reachable
        for _ in range(_REACHABILITY_MAX_PROBES):
            if not self.is_running:
                # cloudflared died — no point waiting
                break
            if time.monotonic() >= deadline:
                break
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status < 600:
                        # Any HTTP response (even 4xx/5xx) means the tunnel is up
                        return url
            except urllib.error.HTTPError as e:
                # An HTTP error from Cloudflare's edge means the tunnel IS routed
                if e.code != 520:  # 520 = "web server returned unknown error"
                    return url
            except (urllib.error.URLError, OSError):
                # Not reachable yet — wait and retry
                pass
            time.sleep(_REACHABILITY_PROBE_INTERVAL)

        # Return the URL anyway — user can try; Cloudflare may still be propagating
        return url

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()