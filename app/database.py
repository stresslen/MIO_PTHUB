from __future__ import annotations

from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

# Setup SQLite engine with foreign key support and WAL mode for better concurrency
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=settings.debug,
    future=True,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables and run automatic migrations."""
    import app.models.lead  # noqa: F401
    import app.models.source  # noqa: F401
    import app.models.organization  # noqa: F401
    import app.models.setting  # noqa: F401
    import app.models.keyword  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # SQLite column migration check
    with engine.connect() as conn:
        try:
            # Check if sales_strategy column exists in leads
            result = conn.exec_driver_sql("PRAGMA table_info(leads)")
            columns = [row[1] for row in result.fetchall()]
            migrations = {
                "sales_strategy": "ALTER TABLE leads ADD COLUMN sales_strategy TEXT",
                "organization_id": "ALTER TABLE leads ADD COLUMN organization_id VARCHAR(36)",
                "enrichment_status": "ALTER TABLE leads ADD COLUMN enrichment_status VARCHAR(50)",
                "enrichment_message": "ALTER TABLE leads ADD COLUMN enrichment_message TEXT",
            }
            for column, statement in migrations.items():
                if column not in columns and len(columns) > 0:
                    conn.exec_driver_sql(statement)
            conn.commit()
        except Exception:
            pass
