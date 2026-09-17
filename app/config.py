from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
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

    secret_key: str = "change-me-in-production"
    session_max_age: int = 60 * 60 * 24 * 14  # 14 days

    def model_post_init(self, __context) -> None:
        if not self.database_url:
            self.database_url = f"sqlite:///{(BASE_DIR / 'invoices.db').as_posix()}"

    @property
    def upload_path(self) -> Path:
        path = BASE_DIR / self.upload_dir
        path.mkdir(exist_ok=True)
        return path


settings = Settings()