from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # GCP
    gcp_project_id: str = "project-901e5f96-55af-4675-abe"
    gcp_region: str = "us-central1"

    # Database — updated defaults for csql-workbrain / workbrain_user # update password during deployment
    db_user: str = "workbrain_user"       # dedicated app user — upsert access only
    db_password: str = "password"         # update password during deployment
    database_url: str = f"postgresql+asyncpg://{db_user}:{db_password}@127.0.0.1:5432/workbrain"
    cloud_sql_instance: str = ""          # e.g. your-project:us-central1:csql-workbrain
    db_name: str = "workbrain"
    db_schema: str = "workbrain_schema"   # PostgreSQL schema inside the database

    # Vertex AI
    vertex_ai_model: str = "gemini-2.0-flash-001"
    vertex_ai_location: str = "us-central1"

    # Google OAuth
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_token_path: str = "./token.json"

    # App
    app_env: str = "development"
    user_id: str = "demo_user"
    daily_capacity_minutes: float = 480.0
    overload_threshold: float = 0.85
    frontend_url: str = "http://localhost:3000"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def overload_limit(self) -> float:
        return self.daily_capacity_minutes * self.overload_threshold

    def get_db_url(self) -> str:
        """
        Build the async SQLAlchemy connection URL.

        Key change from default:
        - Uses workbrain_user instead of postgres
        - Appends options=-csearch_path%3Dworkbrain_schema so SQLAlchemy
          always resolves unqualified table names inside workbrain_schema.
          (The ALTER ROLE ... SET search_path in schema.sql also handles this,
           but setting it in the URL is belt-and-suspenders for Cloud Run.)
        """
        schema_option = f"options=-csearch_path%3D{self.db_schema}"

        if self.is_production and self.cloud_sql_instance:
            # Cloud Run → Cloud SQL via Unix socket (no proxy needed in prod)
            return (
                f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
                f"@/{self.db_name}"
                f"?host=/cloudsql/{self.cloud_sql_instance}"
                f"&{schema_option}"
            )

        # Local dev — connects via Cloud SQL Proxy on 127.0.0.1:5432
        # Strip any existing options param from DATABASE_URL before appending
        base = self.database_url.split("?")[0]
        return f"{base}?{schema_option}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
