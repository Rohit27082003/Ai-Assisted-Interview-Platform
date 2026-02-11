"""add interview time window

Revision ID: add_interview_time_window
Revises:
Create Date: 2026-02-10 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_interview_time_window'
down_revision = '3de2e48f4a49'  # verify_tables
branch_labels = None
depends_on = None


def upgrade():
    """Add interview_window_start and interview_window_end columns to candidates table."""
    op.add_column('candidates', sa.Column('interview_window_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('candidates', sa.Column('interview_window_end', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    """Remove interview_window_start and interview_window_end columns from candidates table."""
    op.drop_column('candidates', 'interview_window_end')
    op.drop_column('candidates', 'interview_window_start')
