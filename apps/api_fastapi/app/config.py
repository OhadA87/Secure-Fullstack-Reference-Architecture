from typing import List, Optional

from pydantic import Field, validator
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
    DEBUG: bool = Field(default=True, description="Debug mode")
    
    # Database Configuration
    DB_DSN: str = Field(
        default="postgresql+asyncpg://spotify:spotify@localhost:5432/spotify_dev",
        description="Database connection string"
    )
    DB_POOL_SIZE: int = Field(default=20, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=30, description="Database max overflow connections")
    DB_POOL_RECYCLE: int = Field(default=300, description="Database pool recycle time (seconds)")
    DB_ECHO: bool = Field(default=False, description="Log all SQL queries")
    
    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    REDIS_CACHE_DB: int = Field(default=0, description="Redis database for caching")
    REDIS_SESSION_DB: int = Field(default=1, description="Redis database for sessions")
    REDIS_RATE_LIMIT_DB: int = Field(default=2, description="Redis database for rate limiting")
    REDIS_MAX_CONNECTIONS: int = Field(default=50, description="Redis max connections")
    
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
    
    # CORS & Security
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins"
    )
    ALLOWED_HOSTS: List[str] = Field(
        default=["localhost", "127.0.0.1", "*.spotify-clone.com"],
        description="Allowed host headers"
    )
    TRUSTED_PROXIES: List[str] = Field(
        default=["127.0.0.1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
        description="Trusted proxy IP ranges"
    )
    
    # Rate Limiting
    RATE_LIMIT_STORAGE_URL: str = Field(
        default="redis://localhost:6379/2",
        description="Rate limiting storage URL"
    )
    DEFAULT_RATE_LIMIT: str = Field(
        default="100/minute",
        description="Default rate limit for all endpoints"
    )
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(default="json", description="Log format (json/text)")
    
    # Security
    BCRYPT_ROUNDS: int = Field(default=12, description="Bcrypt rounds for password hashing")
    SESSION_COOKIE_SECURE: bool = Field(default=True, description="Secure session cookies")
    SESSION_COOKIE_HTTPONLY: bool = Field(default=True, description="HTTP-only session cookies")
    SESSION_COOKIE_SAMESITE: str = Field(default="lax", description="SameSite cookie policy")
    
    # API Configuration
    API_TITLE: str = Field(default="Spotify Clone API", description="API title")
    API_DESCRIPTION: str = Field(
        default="Production-ready FastAPI with security, observability, and scalability",
        description="API description"
    )
    API_VERSION: str = Field(default="1.0.0", description="API version")
    DOCS_URL: Optional[str] = Field(default="/docs", description="Swagger docs URL")
    REDOC_URL: Optional[str] = Field(default="/redoc", description="ReDoc URL")
    
    # Observability
    ENABLE_METRICS: bool = Field(default=True, description="Enable Prometheus metrics")
    METRICS_PATH: str = Field(default="/metrics", description="Metrics endpoint path")
    
    # Datadog (optional)
    DD_TRACE_ENABLED: bool = Field(default=False, description="Enable Datadog tracing")
    DD_SERVICE: str = Field(default="spotify-clone-api", description="Datadog service name")
    DD_ENV: str = Field(default="dev", description="Datadog environment")
    DD_VERSION: str = Field(default="1.0.0", description="Datadog version")
    DD_AGENT_HOST: str = Field(default="localhost", description="Datadog agent host")
    DD_AGENT_PORT: int = Field(default=8126, description="Datadog agent port")
    
    # File Upload
    MAX_UPLOAD_SIZE: int = Field(default=10 * 1024 * 1024, description="Max upload size (10MB)")
    UPLOAD_DIR: str = Field(default="uploads", description="Upload directory")
    
    # External Services
    SPOTIFY_API_BASE_URL: str = Field(
        default="https://api.spotify.com/v1",
        description="Spotify API base URL"
    )
    SPOTIFY_CLIENT_ID: Optional[str] = Field(default=None, description="Spotify client ID")
    SPOTIFY_CLIENT_SECRET: Optional[str] = Field(default=None, description="Spotify client secret")

    @validator("ALLOWED_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("ALLOWED_HOSTS", pre=True)
    def parse_allowed_hosts(cls, v):
        """Parse allowed hosts from string or list."""
        if isinstance(v, str):
            return [host.strip() for host in v.split(",")]
        return v
    
    @validator("JWT_SECRET")
    def validate_jwt_secret(cls, v, values):
        """Validate JWT secret strength."""
        env = values.get("ENV", "dev")
        if env == "prod" and v == "dev-secret-change-in-production":
            raise ValueError("JWT_SECRET must be changed in production")
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return v
    
    @validator("DB_DSN")
    def validate_database_url(cls, v):
        """Validate database URL format."""
        valid_schemes = ("postgresql://", "postgresql+asyncpg://", "sqlite+aiosqlite://")
        if not v.startswith(valid_schemes):
            raise ValueError(f"DB_DSN must start with one of: {valid_schemes}")
        return v

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENV.lower() == "prod"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENV.lower() == "dev"
    
    def is_staging(self) -> bool:
        """Check if running in staging environment."""
        return self.ENV.lower() == "staging"
    
    def get_database_url(self) -> str:
        """Get database URL for SQLAlchemy."""
        return self.DB_DSN
    
    def get_redis_url(self, db: Optional[int] = None) -> str:
        """Get Redis URL for specific database."""
        if db is not None:
            base_url = self.REDIS_URL.split("/")[0] + "//"
            if "@" in self.REDIS_URL:
                # Has auth: redis://user:pass@host:port/db
                auth_host = self.REDIS_URL.split("//")[1].split("/")[0]
                return f"{base_url}{auth_host}/{db}"
            else:
                # No auth: redis://host:port/db
                host_port = self.REDIS_URL.split("//")[1].split("/")[0]
                return f"{base_url}{host_port}/{db}"
        return self.REDIS_URL
    
    def get_docs_url(self) -> Optional[str]:
        """Get docs URL based on environment."""
        if self.is_production():
            return None  # Disable docs in production
        return self.DOCS_URL
    
    def get_redoc_url(self) -> Optional[str]:
        """Get ReDoc URL based on environment."""
        if self.is_production():
            return None  # Disable ReDoc in production
        return self.REDOC_URL


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get settings instance (for dependency injection)."""
    return settings