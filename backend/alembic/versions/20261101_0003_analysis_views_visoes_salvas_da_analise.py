"""analysis views: visoes salvas da analise

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01 22:04:59.253200
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('analysis_views',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('dashboard_id', sa.UUID(), nullable=False),
    sa.Column('owner_user_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['dashboard_id'], ['dashboards.id'], name=op.f('fk_analysis_views_dashboard_id_dashboards'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_analysis_views_owner_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_views'))
    )
    op.create_index(op.f('ix_analysis_views_dashboard_id'), 'analysis_views', ['dashboard_id'], unique=False)
    op.create_index('uq_analysis_views_owner_name', 'analysis_views', ['dashboard_id', 'owner_user_id', 'name'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_analysis_views_owner_name', table_name='analysis_views')
    op.drop_index(op.f('ix_analysis_views_dashboard_id'), table_name='analysis_views')
    op.drop_table('analysis_views')
