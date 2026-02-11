"""add JD-level interview time windows

Revision ID: add_jd_level_time_windows
Revises: add_interview_time_window
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_jd_level_time_windows'
down_revision = 'add_interview_time_window'
branch_labels = None
depends_on = None


def upgrade():
    """Add interview_window_start and interview_window_end columns to job_descriptions table."""
    op.add_column('job_descriptions', sa.Column('interview_window_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('job_descriptions', sa.Column('interview_window_end', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    """Remove interview time window columns from job_descriptions table."""
    op.drop_column('job_descriptions', 'interview_window_end')
    op.drop_column('job_descriptions', 'interview_window_start')
