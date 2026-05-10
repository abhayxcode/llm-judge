from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WORKERS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="local")

    redis_url: str = Field(default="redis://localhost:6380/0", alias="REDIS_URL")
    queue_name: str = Field(default="judge-default")

    stream_name: str = Field(default="judge:traces")
    consumer_group: str = Field(default="judge-workers")
    consumer_name: str = Field(default="worker-1")
    block_ms: int = Field(default=5_000)
    batch_size: int = Field(default=64)

    eval_stream_name: str = Field(default="judge:evals")
    eval_consumer_group: str = Field(default="judge-eval-workers")
    eval_consumer_name: str = Field(default="eval-worker-1")
    eval_concurrency: int = Field(default=8)

    ch_host: str = Field(default="localhost", alias="CH_HOST")
    ch_http_port: int = Field(default=8123, alias="CH_HTTP_PORT")
    ch_user: str = Field(default="judge", alias="CH_USER")
    ch_password: str = Field(default="judge", alias="CH_PASSWORD")
    ch_db: str = Field(default="judge", alias="CH_DB")

    pg_host: str = Field(default="localhost", alias="PG_HOST")
    pg_port: int = Field(default=5432, alias="PG_PORT")
    pg_user: str = Field(default="judge", alias="PG_USER")
    pg_password: str = Field(default="judge", alias="PG_PASSWORD")
    pg_db: str = Field(default="judge", alias="PG_DB")

    @property
    def pg_async_url(self) -> str:
        return f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_db}"


def get_settings() -> Settings:
    return Settings()
