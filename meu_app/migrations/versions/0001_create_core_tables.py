"""create core tables"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'clients',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255)),
        sa.Column('status', sa.String(length=32), server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index(op.f('ix_clients_phone'), 'clients', ['phone'], unique=True)

    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('phase', sa.String(length=32), server_default='ATENDIMENTO'),
        sa.Column('last_intent', sa.String(length=64)),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index(op.f('ix_sessions_client_id'), 'sessions', ['client_id'], unique=False)

    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('sessions.id'), nullable=False),
        sa.Column('provider_msg_id', sa.String(length=128)),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('topic', sa.String(length=64)),
        sa.Column('intent', sa.String(length=64)),
        sa.Column('entities_json', sa.JSON()),
        sa.Column('sources_json', sa.JSON()),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_index('ix_messages_provider_unique', 'messages', ['provider_msg_id'])


def downgrade() -> None:
    op.drop_index('ix_messages_provider_unique', table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_sessions_client_id'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_index(op.f('ix_clients_phone'), table_name='clients')
    op.drop_table('clients')