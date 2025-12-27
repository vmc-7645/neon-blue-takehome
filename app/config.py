from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    api_tokens: str  # comma-separated allowlist

    @property
    def token_set(self) -> set[str]:
        return {t.strip() for t in self.api_tokens.split(",") if t.strip()}

settings = Settings()
