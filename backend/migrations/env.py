from pathlib import Path

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.store import database_url

url = make_url(database_url())
if url.database and url.database != ":memory:":
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)
with create_engine(url).begin() as connection:
    context.configure(connection=connection)
    context.run_migrations()
