from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    llm_base_url: str = "http://80.82.59.87:8080/v1"
    llm_timeout: int = 1800
    llm_max_tokens: int = 4096
    rss_default_interval_min: int = 15
    rss_cycle_interval_min: int = 5
    tg_bot_token: str = ""
    database_url: str = "sqlite:///./smart_stream.db"

    model_config = {"env_file": ".env"}


settings = Settings()
