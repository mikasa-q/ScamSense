from alembic import op
import sqlalchemy as sa

revision = "0001_sessions"
down_revision = None


def upgrade():
    op.create_table(
        "sessions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("create_key", sa.String, nullable=False, unique=True),
        sa.Column("token_hash", sa.LargeBinary, nullable=False),
        sa.Column("expires_at", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("state", sa.JSON, nullable=False),
    )


def downgrade():
    op.drop_table("sessions")
