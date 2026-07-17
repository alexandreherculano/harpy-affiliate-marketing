"""Configuration management via environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_max_tokens: int = 4096
    deepseek_temperature: float = 0.7

    output_dir: str = "outputs/flywheels"
    log_dir: str = "logs"
    skills_dir: str = "skills/affiliate-skills"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)

    @property
    def skills_path(self) -> Path:
        return Path(self.skills_dir)

    @property
    def log_path(self) -> Path:
        return Path(self.log_dir)

    def validate_api_key(self) -> None:
        if not self.deepseek_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is required. Set it in .env file or environment."
            )


_config: Config | None = None


def load_config(env_file: str = ".env", require_api_key: bool = True) -> Config:
    global _config
    if _config is not None:
        return _config

    if os.path.exists(env_file):
        load_dotenv(env_file)

    try:
        _config = Config()
    except ValidationError as e:
        raise ValueError(f"Invalid configuration: {e}") from e

    if require_api_key:
        _config.validate_api_key()
    return _config


def get_config() -> Config:
    if _config is None:
        return load_config()
    return _config
