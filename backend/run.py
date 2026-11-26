"""
Application launch script.
Executes Uvicorn server with hot reload support in development.
"""
import sys
from pathlib import Path
import uvicorn

# Ensure backend root is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import get_settings

if __name__ == "__main__":
    settings = get_settings()
    use_tls = bool(settings.SSL_CERTFILE and settings.SSL_KEYFILE)
    scheme = "https" if use_tls else "http"
    print(f"Launching {settings.PROJECT_NAME} on {scheme}://127.0.0.1:8000...")

    run_kwargs = {
        "app_dir": str(BACKEND_DIR),
        "host": "127.0.0.1",
        "port": 8000,
        "reload": settings.DEBUG,
        "reload_dirs": [str(BACKEND_DIR)],
        "log_level": "info",
    }
    if use_tls:
        run_kwargs["ssl_certfile"] = settings.SSL_CERTFILE
        run_kwargs["ssl_keyfile"] = settings.SSL_KEYFILE

    uvicorn.run("app.main:app", **run_kwargs)
