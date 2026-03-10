import os
from pathlib import Path

import uvicorn

from .api import create_app


def _load_dotenv() -> None:
    """Load .env file from project root if it exists. No external dependency needed."""
    for candidate in [Path.cwd() / ".env", Path(__file__).resolve().parents[3] / ".env"]:
        if candidate.is_file():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Don't override already-set env vars.
                if key and key not in os.environ:
                    os.environ[key] = value
            break


def main() -> None:
    _load_dotenv()
    host = os.getenv("ODP_HOST", "127.0.0.1")
    port = int(os.getenv("ODP_PORT", "8080"))
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
