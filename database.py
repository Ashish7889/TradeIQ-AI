import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

# Ensure data directory exists for SQLite
os.makedirs("data", exist_ok=True)

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/stocksense.db")

# Dynamic DB Engine selection (Startup scaling ready)
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL institutional pooling config
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, 
        pool_size=10, 
        max_overflow=20,
        pool_pre_ping=True
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency payload
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
