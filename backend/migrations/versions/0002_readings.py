"""photo readings"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "readings",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("watch_id", sa.Uuid, sa.ForeignKey("watches.id"), nullable=False, index=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("offset_seconds", sa.Float, nullable=False),
        sa.Column("reset", sa.Boolean, nullable=False),
        sa.Column("photo_key", sa.String(200)),
    )


def downgrade() -> None:
    op.drop_table("readings")
