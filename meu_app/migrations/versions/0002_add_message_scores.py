"""add coverage and retrieval scores to messages"""

from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('coverage', sa.Float(), nullable=True))
    op.add_column('messages', sa.Column('retrieval_scores_json', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'retrieval_scores_json')
    op.drop_column('messages', 'coverage')