from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://aquadoks_user:aquadoks_pass_change_in_prod@localhost:5432/aquadoks"

    # Telegram
    telegram_bot_token: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Yandex GPT
    yandex_api_key: str = ""
    yandex_folder_id: str = ""

    # Admin bot
    admin_bot_token: str = ""
    admin_bot_password: str = ""

    # Robokassa
    robokassa_merchant_login: str = ""
    robokassa_password_1: str = ""
    robokassa_password_2: str = ""
    robokassa_test_mode: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
