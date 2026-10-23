"""Hermes Print Automation - System Configuration.

Manages environment variables, hardware settings, AI credentials,
pricing logic, and paths with strict Pydantic validation.
"""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --- Fonnte WhatsApp Gateway ---
    FONNTE_API_TOKEN: str = Field(
        default="",
        description="Fonnte Device API Token from md.fonnte.com"
    )
    FONNTE_API_URL: str = Field(
        default="https://api.fonnte.com",
        description="Base URL for Fonnte HTTP API"
    )
    ADMIN_WHATSAPP_NUMBER: str = Field(
        default="",
        description="WhatsApp number to receive escalated document design/content revision requests"
    )

    # --- AI Agent ('Hermes') ---
    AI_PROVIDER: str = Field(
        default="gemini",
        description="AI LLM Provider: 'gemini' or 'openai'"
    )
    GEMINI_API_KEY: str = Field(
        default="",
        description="Google Gemini API Key from Google AI Studio"
    )
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API Key (if AI_PROVIDER is openai)"
    )
    OPENAI_BASE_URL: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI API Base URL (support 9Router, Ollama, LM Studio, etc.)"
    )
    AI_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Model ID (e.g. gemini-2.5-flash, Kenari/deepseek-v4-1-flash:free, gpt-4o-mini)"
    )

    # --- Printer Hardware & Spooler ---
    PRINTER_OS: str = Field(
        default="windows",
        description="Target Operating System: 'windows' or 'linux'"
    )
    PRINTER_NAME: str = Field(
        default="",
        description="Exact printer name in OS (leave blank to auto-detect system default)"
    )
    SUMATRAPDF_PATH: str = Field(
        default="SumatraPDF.exe",
        description="SumatraPDF binary path or command name"
    )
    PRINT_SIMULATION_MODE: bool = Field(
        default=False,
        description="If True, print commands will be logged and simulated without executing physical spooling"
    )

    # --- Business Pricing Rules (IDR) ---
    PRICE_PER_PAGE_BW: int = Field(
        default=500,
        description="Tarif cetak per halaman Hitam-Putih (IDR)"
    )
    PRICE_COLOR_LOW: int = Field(
        default=2000,
        description="Tarif cetak warna < 50% per halaman (IDR)"
    )
    PRICE_COLOR_HIGH: int = Field(
        default=2500,
        description="Tarif cetak warna >= 50% per halaman (IDR)"
    )
    PRICE_COLOR_FULL: int = Field(
        default=3000,
        description="Tarif cetak full warna per halaman (IDR)"
    )
    PRICE_PER_PAGE_COLOR: int = Field(
        default=2000,
        description="Default fallback tarif warna (IDR)"
    )
    STORE_NAME: str = Field(
        default="Hermes Digital Print",
        description="Store/Service name for messages"
    )

    # --- Storage & Database ---
    STORAGE_DIR: str = Field(
        default="storage/temp_pdfs",
        description="Relative or absolute path for storing incoming PDFs"
    )
    DATABASE_PATH: str = Field(
        default="storage/hermes.db",
        description="SQLite database path"
    )

    # --- Server Binding ---
    HOST: str = Field(default="0.0.0.0", description="FastAPI host")
    PORT: int = Field(default=8000, description="FastAPI port")

    @property
    def storage_dir_path(self) -> Path:
        """Resolve and ensure the temporary PDF storage folder exists."""
        p = Path(self.STORAGE_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def database_file_path(self) -> Path:
        """Resolve and ensure the SQLite database directory exists."""
        p = Path(self.DATABASE_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
