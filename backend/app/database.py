from collections.abc import Generator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://brewbill:brewbill@localhost:5432/brewbill"
    jwt_secret: str = "development-only-change-me-at-least-32-bytes"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 30
    offline_license_hours: int = 48
    license_refresh_hours: int = 6
    license_private_key: str = ''
    license_public_key: str = ''
    cors_origins: str = 'http://localhost:4200,http://127.0.0.1:4200,null'
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
