# A-tunnel
A minimal Python package to expose localhost to the public internet using [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

No Cloudflare account required  generates a temporary `*.trycloudflare.com` URL.

## Installation

```bash
# Using pip
pip install atunnel

# Or using uv
uv add atunnel
```

## Usage

### CLI

```bash
# Expose local port 8080
atunnel --port 8080

# With uv
uv run atunnel --port 8080
```

The public URL is printed to stdout. Press Ctrl+C to stop.

### Python API

```python
from atunnel.tunnel import Tunnel

with Tunnel(port=8080) as t:
    print(f"Public URL: {t.public_url}")
    input("Press Enter to stop...")
```

## On Pypi:
[A-tunnel](https://pypi.org/project/atunnel/)
