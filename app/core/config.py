"""Application configuration using Pydantic Settings."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/metering_billing",
        alias="DATABASE_URL",
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/metering_billing",
        alias="DATABASE_URL_SYNC",
    )

    # Stripe (test mode only)
    stripe_secret_key: str = Field(default="", alias="STRIPE_SECRET_KEY")
    stripe_publishable_key: str = Field(default="", alias="STRIPE_PUBLISHABLE_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_id_free: str = Field(default="price_free_monthly", alias="STRIPE_PRICE_ID_FREE")
    stripe_price_id_pro: str = Field(default="price_pro_monthly", alias="STRIPE_PRICE_ID_PRO")

    # Application
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Pricing constants (in cents per unit)
    price_api_call_cents: int = Field(default=1, alias="PRICE_API_CALL_CENTS")
    price_input_token_per_million_cents: int = Field(default=150, alias="PRICE_INPUT_TOKEN_PER_MILLION_CENTS")
    price_cached_input_token_per_million_cents: int = Field(default=37, alias="PRICE_CACHED_INPUT_TOKEN_PER_MILLION_CENTS")
    price_output_token_per_million_cents: int = Field(default=600, alias="PRICE_OUTPUT_TOKEN_PER_MILLION_CENTS")
    price_reasoning_token_per_million_cents: int = Field(default=600, alias="PRICE_REASONING_TOKEN_PER_MILLION_CENTS")

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def is_test(self) -> bool:
        return self.app_env.lower() == "test"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()