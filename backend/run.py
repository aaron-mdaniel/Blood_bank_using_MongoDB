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
    print(f"Launching {settings.PROJECT_NAME} on http://127.0.0.1:8000...")
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
