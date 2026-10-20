import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hackpilot.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate():
    """Create tables and add columns introduced after the first release, so an existing hackpilot.db keeps working."""
    from sqlalchemy import inspect, text
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    with engine.begin() as c:
        for table in ("deadlines", "checklist_items"):
            if "external_id" not in [col["name"] for col in insp.get_columns(table)]:
                c.execute(text(f"ALTER TABLE {table} ADD COLUMN external_id VARCHAR(100)"))
            c.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{table}_external_id ON {table}(external_id)"))
