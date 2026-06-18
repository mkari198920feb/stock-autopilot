from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        extra="ignore",
    )

    openai_api_key: str = ""
    autopilot_hour: int = 13
    autopilot_minute: int = 30
    target_return_min: float = 0.12
    target_return_max: float = 0.15

    # Email notifications (SMTP)
    email_enabled: bool = False
    email_recipients: str = ""  # comma-separated, merges with config.yaml list
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    dashboard_url: str = ""  # optional link in emails

    project_root: Path = _PROJECT_ROOT
    config_path: Path = project_root / "config.yaml"
    data_dir: Path = project_root / "data"
    db_path: Path = data_dir / "autopilot.db"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
