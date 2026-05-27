"""
Downloads and manages the cloudflared binary for the current platform.
"""

import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional


_GITHUB_RELEASES_BASE = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download"
)

_BINARY_MAP = {
    ("Linux", "x86_64"): "cloudflared-linux-amd64",
    ("Linux", "aarch64"): "cloudflared-linux-arm64",
    ("Linux", "armv7l"): "cloudflared-linux-arm",
    ("Darwin", "x86_64"): "cloudflared-darwin-amd64.tgz",
    ("Darwin", "arm64"): "cloudflared-darwin-arm64.tgz",
    ("Windows", "AMD64"): "cloudflared-windows-amd64.exe",
}


def _cache_dir() -> Path:
    """Return the package-local directory for downloaded binaries."""
    override = os.environ.get("ATUNNEL_BIN_DIR")
    if override:
        return Path(override).expanduser()

    return Path(__file__).parent / "bin"


def _binary_name() -> str:
    if platform.system() == "Windows":
        return "cloudflared.exe"
    return "cloudflared"


def find_binary() -> Optional[Path]:
    """Find an existing cloudflared binary (cache or PATH)."""
    cached = _cache_dir() / _binary_name()
    if cached.exists():
        return cached
    system_bin = shutil.which("cloudflared")
    if system_bin:
        return Path(system_bin)
    return None


def ensure_binary() -> Path:
    """Return path to cloudflared binary, downloading if necessary."""
    existing = find_binary()
    if existing:
        return existing
    return download()


def download() -> Path:
    """Download the cloudflared binary for the current platform."""
    system = platform.system()
    machine = platform.machine()
    filename = _BINARY_MAP.get((system, machine))

    if filename is None:
        raise RuntimeError(
            f"Unsupported platform: {system} {machine}. "
            f"Supported: {list(_BINARY_MAP.keys())}"
        )

    url = f"{_GITHUB_RELEASES_BASE}/{filename}"
    cache = _cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / _binary_name()

    print("Initializing for the first run...", file=sys.stderr)

    if filename.endswith(".tgz"):
        _download_tgz(url, dest)
    else:
        _download_file(url, dest)

    if system != "Windows":
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return dest


def _download_file(url: str, dest: Path) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dest.parent, suffix=".download")
    try:
        os.close(tmp_fd)
        req = urllib.request.Request(url, headers={"User-Agent": "atunnel/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(tmp_path, "wb") as f:
                shutil.copyfileobj(resp, f)
        shutil.move(tmp_path, dest)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _download_tgz(url: str, dest: Path) -> None:
    import tarfile

    tmp_fd, tmp_path = tempfile.mkstemp(dir=dest.parent, suffix=".tgz")
    try:
        os.close(tmp_fd)
        req = urllib.request.Request(url, headers={"User-Agent": "atunnel/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(tmp_path, "wb") as f:
                shutil.copyfileobj(resp, f)

        with tarfile.open(tmp_path, "r:gz") as tar:
            for member in tar.getnames():
                if "cloudflared" in member and not member.endswith("/"):
                    extracted = tar.extractfile(member)
                    if extracted:
                        with open(dest, "wb") as f:
                            shutil.copyfileobj(extracted, f)
                        return
            raise RuntimeError("cloudflared binary not found in archive")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
