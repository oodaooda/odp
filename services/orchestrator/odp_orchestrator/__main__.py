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
                # Strip inline comments (e.g. KEY=value # comment → value).
                if " #" in value:
                    value = value[:value.index(" #")].strip()
                # Strip surrounding quotes (e.g. KEY="value" or KEY='value').
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                # Don't override already-set env vars.
                if key and key not in os.environ:
                    os.environ[key] = value
            break


def main() -> None:
    _load_dotenv()
    host = os.getenv("ODP_HOST", "127.0.0.1")
    port = int(os.getenv("ODP_PORT", "8080"))
    reload = os.getenv("ODP_RELOAD", "1") == "1"
    if reload:
        # reload requires the app as an import string, not an object.
        uvicorn.run(
            "services.orchestrator.odp_orchestrator.api:create_app",
            factory=True, host=host, port=port, log_level="info",
            reload=True, reload_dirs=["services"],
        )
    else:
        uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
