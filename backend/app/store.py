import os

import sqlalchemy as sa


def database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite+pysqlite:///./var/scamsense.db")


sessions = sa.Table(
    "sessions", sa.MetaData(),
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("create_key", sa.String, nullable=False, unique=True),
    sa.Column("token_hash", sa.LargeBinary, nullable=False),
    sa.Column("expires_at", sa.Integer, nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("state", sa.JSON, nullable=False),
)
