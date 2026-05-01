from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # GCP
    gcp_project_id: str = "workbrain-cortexflow-project"
    gcp_region: str = "us-central1"
    google_cloud_project: str = "workbrain-cortexflow-project"
    google_cloud_location: str = "us-central1"

    # AlloyDB
    db_host: str = "host"
    db_port: int = 5432
    db_user: str = "db_user"
    db_password: str = "db_password"
    db_name: str = "workbrain"
    db_schema: str = "workbrain_schema"
    cloud_sql_instance: str = ""  # Not used for AlloyDB

    # Vertex AI
    vertex_ai_model: str = "gemini-2.5-flash"
    vertex_ai_location: str = "us-central1"
    google_genai_use_vertexai: str = "True"

    # OAuth
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_token_path: str = "./token.json"

    # App
    app_env: str = "production"
    user_id: str = "demo_user"
    team_members: dict = {
        "Naveen": "naveenreddym8699@gmail.com",
        "Naveen M": "naveenreddym8699@gmail.com",
        "Ravi": "ravikumar19980816@gmail.com",
        "Ravi Kumar": "ravikumar19980816@gmail.com",
        "_default": "naveenreddym8699@gmail.com",
    }
    daily_capacity_minutes: float = 480.0
    overload_threshold: float = 0.85
    frontend_url: str = "http://localhost:3000"

    # Slack
    slack_bot_token: str = ""
    slack_channel_id: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def overload_limit(self) -> float:
        return self.daily_capacity_minutes * self.overload_threshold

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
