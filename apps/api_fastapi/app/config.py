from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Environment
    ENV: str = Field(default="dev", description="Environment (dev/staging/prod)")
    
    # Database
    DB_DSN: str = Field(
        default="postgresql+asyncpg://spotify:spotify@localhost:5432/spotify_dev",
        description="Database connection string"
    )
    
    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    
    # JWT Configuration
    JWT_SECRET: str = Field(
        default="dev-secret-change-in-production",
        description="JWT signing secret"
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Access token expiry in minutes")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Refresh token expiry in days")
    JWT_AUDIENCE: str = Field(default="spotify-clone", description="JWT audience claim")
    JWT_ISSUER: str = Field(default="spotify-clone-api", description="JWT issuer claim")
    
    # CORS
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins"
    )
    
    # Rate Limiting
    RATE_LIMIT_STORAGE_URL: str = Field(
        default="redis://localhost:6379/1",
        description="Rate limiting storage URL"
    )
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    
    # Security
    BCRYPT_ROUNDS: int = Field(default=12, description="Bcrypt rounds for password hashing")
    
    # AWS Configuration
    AWS_ACCESS_KEY_ID: str = Field(default="", description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: str = Field(default="", description="AWS secret access key")
    AWS_REGION: str = Field(default="us-east-1", description="AWS region")
    S3_BUCKET_NAME: str = Field(default="spotify-clone-audio", description="S3 bucket for audio files")
    CLOUDFRONT_DOMAIN: str = Field(default="", description="CloudFront domain for CDN")

    # Datadog (optional)
    DD_TRACE_ENABLED: bool = Field(default=False, description="Enable Datadog tracing")
    DD_SERVICE: str = Field(default="spotify-clone-api", description="Datadog service name")
    DD_ENV: str = Field(default="dev", description="Datadog environment")
    DD_VERSION: str = Field(default="0.1.0", description="Datadog version")

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENV.lower() == "prod"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENV.lower() == "dev"


# Global settings instance
settings = Settings()