"""initial tables"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("google_sub", sa.String(64), unique=True),
        sa.Column("email", sa.String(320)),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_table(
        "watches",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("brand", sa.String(100)),
        sa.Column("model", sa.String(100)),
        sa.Column("bph", sa.Integer),
        sa.Column("photo_key", sa.String(200)),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_table(
        "measurements",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("watch_id", sa.Uuid, sa.ForeignKey("watches.id"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("audio_key", sa.String(200), nullable=False),
        sa.Column("rate_s_per_day", sa.Float),
        sa.Column("rate_first_half", sa.Float),
        sa.Column("rate_second_half", sa.Float),
        sa.Column("beat_error_ms", sa.Float),
        sa.Column("quality", sa.Float),
        sa.Column("detected_bph", sa.Integer),
        sa.Column("error_reason", sa.String(200)),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("analyzed_at", TZ),
    )


def downgrade() -> None:
    for table in ("measurements", "watches", "sessions", "users"):
        op.drop_table(table)
