from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="local")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=4000)

    pg_host: str = Field(default="localhost", alias="PG_HOST")
    pg_port: int = Field(default=5432, alias="PG_PORT")
    pg_user: str = Field(default="judge", alias="PG_USER")
    pg_password: str = Field(default="judge", alias="PG_PASSWORD")
    pg_db: str = Field(default="judge", alias="PG_DB")

    ch_host: str = Field(default="localhost", alias="CH_HOST")
    ch_http_port: int = Field(default=8123, alias="CH_HTTP_PORT")
    ch_user: str = Field(default="judge", alias="CH_USER")
    ch_password: str = Field(default="judge", alias="CH_PASSWORD")
    ch_db: str = Field(default="judge", alias="CH_DB")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")


def get_settings() -> Settings:
    return Settings()
