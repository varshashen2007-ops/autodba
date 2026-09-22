import re
from functools import lru_cache
from typing import Optional
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "AutoDBA"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    # PostgreSQL configuration
    POSTGRES_HOST: str = Field(default="postgres", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port")
    POSTGRES_DB: str = Field(default="autodba", description="PostgreSQL database name")
    POSTGRES_USER: str = Field(default="autodba", description="PostgreSQL username")
    POSTGRES_PASSWORD: str = Field(default="autodba", description="PostgreSQL password")

    # Optional direct DATABASE_URL override
    DATABASE_URL: Optional[str] = None

    # Connection pool configuration
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # ---------------------------------------------------------------------------
    # Phase 2 — Plan analysis thresholds
    # ---------------------------------------------------------------------------
    # Estimated row count above which a scan or join is considered "large"
    PLAN_LARGE_ROW_THRESHOLD: int = Field(
        default=10_000,
        description="Estimated rows above which a node is considered to touch many rows",
    )
    # Total cost above which any plan node raises concern
    PLAN_HIGH_COST_THRESHOLD: float = Field(
        default=1_000.0,
        description="Plan node total cost above which it is flagged as potentially expensive",
    )
    # Sort node cost above which it is highlighted as a bottleneck candidate
    PLAN_SORT_COST_THRESHOLD: float = Field(
        default=500.0,
        description="Sort node total cost threshold for flagging expensive sorts",
    )
    # Nested-loop cost above which the join is flagged as a bottleneck candidate
    PLAN_NESTED_LOOP_COST_THRESHOLD: float = Field(
        default=1_000.0,
        description="Nested Loop total cost threshold for flagging expensive joins",
    )
    # Minimum estimated rows for an unfiltered sequential scan to be noted
    PLAN_SEQ_SCAN_MIN_ROWS: int = Field(
        default=500,
        description=(
            "Unfiltered sequential scans on relations with fewer estimated rows "
            "than this threshold are not flagged"
        ),
    )
    # Minimum total cost for a FILTERED sequential scan to be flagged.
    # For filtered scans, plan_rows is the estimated OUTPUT (after filter), not
    # the total scanned rows.  Cost is the correct table-size proxy because it
    # reflects reading the full relation regardless of filter selectivity.
    PLAN_SEQ_SCAN_MIN_COST: float = Field(
        default=50.0,
        description=(
            "Minimum total cost for a filtered sequential scan to be flagged as "
            "a potential missing-index candidate"
        ),
    )

    # ---------------------------------------------------------------------------
    # Phase 2 Step 2 — HypoPG Counterfactual Validation thresholds
    # ---------------------------------------------------------------------------
    HYPOPG_MIN_COST_IMPROVEMENT_PERCENT: float = Field(
        default=5.0,
        description=(
            "Minimum percentage cost improvement required for a candidate index "
            "to receive a VALIDATED verdict"
        ),
    )

    # ---------------------------------------------------------------------------
    # Phase 3 Step 1 — Safety & Human Approval Gate configuration
    # ---------------------------------------------------------------------------
    APPROVAL_EXPIRATION_MINUTES: int = Field(
        default=30,
        description="Duration in minutes after which a pending approval request expires",
    )

    # ---------------------------------------------------------------------------
    # Phase 3 Step 3 — Real Runtime Benchmarking configuration
    # ---------------------------------------------------------------------------
    BENCHMARK_RUNS: int = Field(
        default=10,
        description="Number of repeated measurement runs for query benchmarking",
    )
    BENCHMARK_WARMUP_RUNS: int = Field(
        default=2,
        description="Number of warm-up runs to discard before taking benchmark measurements",
    )

    @computed_field
    @property
    def sync_database_url(self) -> str:
        """Constructs or returns a synchronous SQLAlchemy database URL using psycopg."""
        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def safe_database_url(self) -> str:
        """Returns database URL with password masked for safe logging and metrics."""
        url = self.sync_database_url
        if self.POSTGRES_PASSWORD and self.POSTGRES_PASSWORD in url:
            url = url.replace(self.POSTGRES_PASSWORD, "********")
        # Ensure any embedded password in ://user:password@ is masked
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:********@", url)


@lru_cache()
def get_settings() -> Settings:
    return Settings()
