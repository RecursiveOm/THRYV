"""V4 encrypted connections and single-use OAuth state."""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "a402_integrations"
down_revision = "a401_workspace"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration",
        sa.Column("user_id", GUID, sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("service", sa.String(20), primary_key=True),
        sa.Column("ciphertext", sa.Text, nullable=False),
        sa.Column("identity", sa.String(200), nullable=False),
        sa.Column("expires_at", sa.Integer, nullable=False),
        sa.Column("scopes", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_table(
        "oauth_state",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", GUID, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service", sa.String(20), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("verifier", sa.Text, nullable=False),
        sa.Column("scopes", sa.Text, nullable=False),
        sa.Column("expires_at", sa.Integer, nullable=False),
    )
    op.create_index("ix_oauth_state_user_id", "oauth_state", ["user_id"])


def downgrade():
    op.drop_table("oauth_state")
    op.drop_table("integration")
