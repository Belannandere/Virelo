from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Все настройки читаются из файла .env в корне проекта."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    upload_dir: str = "uploads"
    max_upload_mb: int = 10
    database_url: str = ""

    def model_post_init(self, __context) -> None:
        # Если DATABASE_URL не задан в .env — строим абсолютный путь
        # к invoices.db в корне проекта. Так база всегда одна,
        # независимо от того, из какой папки запущен uvicorn.
        if not self.database_url:
            self.database_url = (
                f"sqlite:///{(BASE_DIR / 'invoices.db').as_posix()}"
            )

    @property
    def upload_path(self) -> Path:
        path = BASE_DIR / self.upload_dir
        path.mkdir(exist_ok=True)
        return path


# ВАЖНО: этот объект импортируют другие модули (app.ai, app.database, ...).
# Без него получим ImportError: cannot import name 'settings'.
settings = Settings()