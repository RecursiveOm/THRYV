"""V3 owned public research context and existing action audit extension."""

import sqlalchemy as sa
from alembic import op

revision = "37d6a04b213a"
down_revision = "6c9c73ac0555"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversation", sa.Column("browser_state", sa.Text(), nullable=False, server_default="{}")
    )
    with op.batch_alter_table("action") as batch:
        batch.alter_column("device_id", existing_type=sa.String(36), nullable=True)
        batch.add_column(sa.Column("details", sa.Text(), nullable=False, server_default="{}"))


def downgrade():
    # Research audit rows have no device. Do not silently delete them during downgrade.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM action WHERE device_id IS NULL")).scalar():
        raise RuntimeError("Export/remove research audit rows explicitly before downgrading V3.")
    with op.batch_alter_table("action") as batch:
        batch.drop_column("details")
        batch.alter_column("device_id", existing_type=sa.String(36), nullable=False)
    op.drop_column("conversation", "browser_state")
