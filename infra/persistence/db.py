from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from infra.config import settings


BASE_DIR = settings.base_dir
DB_PATH = settings.database_path or (BASE_DIR / "data" / "sisges.db")
DATABASE_URL = settings.database_url


def get_connect_args(database_url: str) -> dict:
    url = make_url(database_url)
    if url.drivername.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def get_engine_kwargs(database_url: str) -> dict:
    url = make_url(database_url)
    kwargs = {
        "connect_args": get_connect_args(database_url),
        "echo": settings.database_echo,
    }
    if not url.drivername.startswith("sqlite"):
        kwargs.update(
            {
                "pool_size": settings.database_pool_size,
                "max_overflow": settings.database_max_overflow,
                "pool_recycle": settings.database_pool_recycle_seconds,
                "pool_pre_ping": settings.database_pool_pre_ping,
            }
        )
    return kwargs


if settings.database_path:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, **get_engine_kwargs(DATABASE_URL))

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
