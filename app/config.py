from __future__ import annotations

from functools import lru_cache
from typing import Optional, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration loaded from environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="")

    deepseek_api_key: Optional[str] = Field(default=None, alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")
    tavily_api_key: Optional[str] = Field(default=None, alias="TAVILY_API_KEY")
    ocr_api_url: Optional[str] = Field(default=None, alias="OCR_API_URL")
    ocr_api_token: Optional[str] = Field(default=None, alias="OCR_API_TOKEN")
    ocr_api_ip: Optional[str] = Field(default=None, alias="OCR_API_IP")
    ocr_api_host: Optional[str] = Field(default=None, alias="OCR_API_HOST")
    asr_app_id: Optional[str] = Field(default=None, alias="ASR_APP_ID")
    asr_api_key: Optional[str] = Field(default=None, alias="ASR_API_KEY")
    asr_secret_key: Optional[str] = Field(default=None, alias="ASR_SECRET_KEY")

    mcp_config_path: str = Field(default="mcp_servers.json", alias="MCP_CONFIG_PATH")
    fs_allowed_dir_1: Optional[str] = Field(default=None, alias="FS_ALLOWED_DIR_1")
    fs_allowed_dir_2: Optional[str] = Field(default=None, alias="FS_ALLOWED_DIR_2")
    ocr_segment_debug: Optional[str] = Field(default=None, alias="OCR_SEGMENT_DEBUG")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    def fs_roots(self) -> List[str]:
        return [path for path in (self.fs_allowed_dir_1, self.fs_allowed_dir_2) if path]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
