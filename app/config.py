from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    secret_key: str
    env: str = "local"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


settings = Settings()
