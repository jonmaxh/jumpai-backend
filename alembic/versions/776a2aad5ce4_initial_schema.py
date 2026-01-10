"""initial schema

Revision ID: 776a2aad5ce4
Revises:
Create Date: 2026-01-10 22:28:14.532581

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '776a2aad5ce4'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('picture', sa.String(500), nullable=True),
        sa.Column('auto_sync_enabled', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # Gmail accounts table
    op.create_table(
        'gmail_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('access_token', sa.LargeBinary(), nullable=False),
        sa.Column('refresh_token', sa.LargeBinary(), nullable=True),
        sa.Column('token_expiry', sa.DateTime(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('last_history_id', sa.String(50), nullable=True),
        sa.Column('watch_expiration', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gmail_accounts_id'), 'gmail_accounts', ['id'], unique=False)

    # Categories table
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_categories_id'), 'categories', ['id'], unique=False)

    # Emails table
    op.create_table(
        'emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gmail_account_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('gmail_message_id', sa.String(255), nullable=False),
        sa.Column('thread_id', sa.String(255), nullable=True),
        sa.Column('subject', sa.String(500), nullable=True),
        sa.Column('sender', sa.String(255), nullable=True),
        sa.Column('sender_email', sa.String(255), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=True, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.ForeignKeyConstraint(['gmail_account_id'], ['gmail_accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_emails_gmail_message_id'), 'emails', ['gmail_message_id'], unique=False)
    op.create_index(op.f('ix_emails_id'), 'emails', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_emails_id'), table_name='emails')
    op.drop_index(op.f('ix_emails_gmail_message_id'), table_name='emails')
    op.drop_table('emails')

    op.drop_index(op.f('ix_categories_id'), table_name='categories')
    op.drop_table('categories')

    op.drop_index(op.f('ix_gmail_accounts_id'), table_name='gmail_accounts')
    op.drop_table('gmail_accounts')

    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
