"""
Application settings and configuration management using Pydantic Settings.
Loads configuration from environment variables and .env file.
"""
from functools import lru_cache
from pathlib import Path
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory paths
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """
    Core application configuration settings.
    Guarantees strict type validation and secure environment variable parsing.
    """
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # General Environment
    ENVIRONMENT: str = Field(default="development", description="Environment: development, testing, production")
    DEBUG: bool = Field(default=True, description="Enable debug mode")
    PROJECT_NAME: str = Field(default="Secure Centralized Blood Bank Management System", description="System Name")
    API_V1_PREFIX: str = Field(default="/api", description="API route prefix")

    # MongoDB Configuration
    MONGODB_URL: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URI")
    DATABASE_NAME: str = Field(default="secure_blood_bank", description="Active MongoDB database name")
    MONGODB_TIMEOUT_MS: int = Field(default=5000, description="Server selection timeout in milliseconds")

    # Cryptography & Security - JWT
    JWT_SECRET_KEY: str = Field(
        default="e3d9b81f03042012d036f740dafceedd86cb63e37cd6d126cee386b2849c9513",
        description="Cryptographic secret key for signing JWT tokens"
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, description="Access token lifespan in minutes")

    # Cryptography & Security - AES-256-GCM
    ENCRYPTION_SECRET_KEY: str = Field(
        default="p+6ZOT6JUpkBW4pzeS1mdYk4sfBkqGNi1RieltE+z8U=",
        description="Base64-encoded 32-byte secret key for AES-256-GCM sensitive field encryption"
    )

    # Cryptography & Security - Argon2id Password Hashing
    ARGON2_TIME_COST: int = Field(default=3, description="Argon2id time cost (iterations)")
    ARGON2_MEMORY_COST: int = Field(default=65536, description="Argon2id memory cost in KiB (64 MiB)")
    ARGON2_PARALLELISM: int = Field(default=4, description="Argon2id parallelism (threads)")

    # CORS Configuration
    CORS_ORIGINS: Union[List[str], str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"],
        description="Allowed CORS origins"
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached application settings instance.
    Uses lru_cache to avoid reading filesystem on repeated dependency calls.
    """
    return Settings()
