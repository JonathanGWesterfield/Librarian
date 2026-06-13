from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///data/librarian.db"
    books_dir: str = "/books"
    codex_broker_url: str = "http://host.docker.internal:8787"
    enable_codex_broker: bool = False

    model_config = SettingsConfigDict(
        env_prefix="LIBRARIAN_",
        env_file=".env",
        extra="ignore",
    )


settings = Settings()

