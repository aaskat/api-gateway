"""Process settings, loaded from environment and an optional .env file.

Pydantic-settings resolves values with this precedence: real environment
variables > .env file > the defaults below. `config` maps to GATEWAYKIT_CONFIG.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GATEWAYKIT_",
        extra="ignore",
    )

    config: str = "gateway.yaml"  # path to the gateway config (env: GATEWAYKIT_CONFIG)
