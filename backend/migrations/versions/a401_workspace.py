"""V4 owned workspace grants.

Revision ID: a401_workspace
Revises: 37d6a04b213a
"""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "a401_workspace"
down_revision = "37d6a04b213a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", GUID, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("device.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
    )
    op.create_index("ix_workspace_user_id", "workspace", ["user_id"])
    op.create_index("ix_workspace_device_id", "workspace", ["device_id"])


def downgrade():
    op.drop_table("workspace")
