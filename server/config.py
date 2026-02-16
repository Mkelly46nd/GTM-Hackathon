import os
from pathlib import Path

# Project root (parent of server/) for importing engines
REPO_ROOT = Path(__file__).resolve().parent.parent

def _get_database_url() -> str:
    db_path = os.environ.get("DATABASE_URL")
    if db_path:
        return db_path
    # Default: sqlite file next to server
    db_file = REPO_ROOT / "server" / "dedup.db"
    return f"sqlite:///{db_file}"


class Settings:
    database_url: str = ""
    clay_webhook_url: str = ""
    n8n_webhook_url: str = ""

    def __init__(self):
        self.database_url = _get_database_url()
        self.clay_webhook_url = os.environ.get("CLAY_WEBHOOK_URL", "")
        self.n8n_webhook_url = os.environ.get("N8N_WEBHOOK_URL", "")


settings = Settings()
