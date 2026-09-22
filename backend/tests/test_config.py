from app.core.config import Settings


def test_settings_defaults():
    settings = Settings(
        DATABASE_URL=None,
        POSTGRES_HOST="dbhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="testdb",
        POSTGRES_USER="testuser",
        POSTGRES_PASSWORD="secretpassword",
    )
    assert settings.PROJECT_NAME == "AutoDBA"
    assert settings.ENVIRONMENT == "development"
    assert settings.HYPOPG_MIN_COST_IMPROVEMENT_PERCENT == 5.0
    assert "postgresql+psycopg://testuser:secretpassword@dbhost:5432/testdb" == settings.sync_database_url


def test_safe_database_url_masks_password():
    settings = Settings(
        DATABASE_URL=None,
        POSTGRES_HOST="dbhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="testdb",
        POSTGRES_USER="testuser",
        POSTGRES_PASSWORD="supersecretpassword123",
    )
    assert "supersecretpassword123" not in settings.safe_database_url
    assert "********" in settings.safe_database_url


def test_database_url_override():
    custom_url = "postgresql://custom_user:custom_pass@otherhost:5433/customdb"
    settings = Settings(DATABASE_URL=custom_url)
    assert "postgresql+psycopg://custom_user:custom_pass@otherhost:5433/customdb" == settings.sync_database_url
    assert "custom_pass" not in settings.safe_database_url
    assert "********" in settings.safe_database_url
