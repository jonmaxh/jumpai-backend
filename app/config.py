from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    google_client_id: str
    google_client_secret: str
    openai_api_key: str
    database_url: str = "sqlite:///./app.db"
    secret_key: str
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    google_redirect_uri: str = ""

    # Gmail Push Notifications (Pub/Sub)
    # Set these when deploying to production with a public URL
    pubsub_topic: str = ""  # Format: projects/{project-id}/topics/{topic-name}
    pubsub_verification_token: str = ""  # Secret token to verify webhook requests

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.google_redirect_uri:
            self.google_redirect_uri = f"{self.backend_url}/api/auth/google/callback"

    @property
    def push_notifications_enabled(self) -> bool:
        """Check if push notifications are configured."""
        return bool(self.pubsub_topic)

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
