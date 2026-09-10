"""Use millisecond timestamps without overflowing PostgreSQL's 32-bit integer."""

import sqlalchemy as sa
from alembic import op

revision = "675b403091a8"
down_revision = "4f853356ea01"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("conversation") as batch:
        batch.alter_column(
            "updated_at", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False
        )


def downgrade():
    # Restore second precision before narrowing the column on PostgreSQL.
    op.execute(
        "UPDATE conversation SET updated_at = updated_at / 1000 WHERE updated_at > 2147483647"
    )
    with op.batch_alter_table("conversation") as batch:
        batch.alter_column(
            "updated_at", existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False
        )
