from arq.connections import RedisSettings

from app.config import get_settings


def redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings.from_dsn(settings.redis_url)

