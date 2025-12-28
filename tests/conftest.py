import os
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import get_db

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", os.getenv("DATABASE_URL"))

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DB_URL)

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.upgrade(alembic_cfg, "head")

    yield engine
    engine.dispose()

@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    tx = connection.begin()

    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    tx.rollback()
    connection.close()

@pytest.fixture(autouse=True)
def override_db(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.clear()
