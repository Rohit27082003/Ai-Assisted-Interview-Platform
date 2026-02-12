"""add evaluation scoring columns

Revision ID: add_evaluation_scoring_columns
Revises: add_jd_level_time_windows
Create Date: 2026-02-12

Adds relevance, practical_application, expected_vs_actual_comparison,
and similarity_score columns to evaluations table.
Also converts integer score columns to float for penalty support.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_evaluation_scoring_columns'
down_revision = 'add_jd_level_time_windows'
branch_labels = None
depends_on = None


def upgrade():
    """Add new scoring columns and convert integer scores to float."""
    # Add new columns
    op.add_column('evaluations', sa.Column('relevance', sa.Float(), server_default='0.0', nullable=True))
    op.add_column('evaluations', sa.Column('practical_application', sa.Float(), server_default='0.0', nullable=True))
    op.add_column('evaluations', sa.Column('expected_vs_actual_comparison', sa.Text(), nullable=True))
    op.add_column('evaluations', sa.Column('similarity_score', sa.Float(), server_default='0.0', nullable=True))

    # Convert existing integer score columns to float for penalty support
    op.alter_column('evaluations', 'correctness', type_=sa.Float(), existing_type=sa.Integer(),
                    postgresql_using='correctness::double precision')
    op.alter_column('evaluations', 'depth', type_=sa.Float(), existing_type=sa.Integer(),
                    postgresql_using='depth::double precision')
    op.alter_column('evaluations', 'reasoning', type_=sa.Float(), existing_type=sa.Integer(),
                    postgresql_using='reasoning::double precision')
    op.alter_column('evaluations', 'clarity', type_=sa.Float(), existing_type=sa.Integer(),
                    postgresql_using='clarity::double precision')


def downgrade():
    """Remove new columns and revert float scores to integer."""
    op.alter_column('evaluations', 'clarity', type_=sa.Integer(), existing_type=sa.Float(),
                    postgresql_using='clarity::integer')
    op.alter_column('evaluations', 'reasoning', type_=sa.Integer(), existing_type=sa.Float(),
                    postgresql_using='reasoning::integer')
    op.alter_column('evaluations', 'depth', type_=sa.Integer(), existing_type=sa.Float(),
                    postgresql_using='depth::integer')
    op.alter_column('evaluations', 'correctness', type_=sa.Integer(), existing_type=sa.Float(),
                    postgresql_using='correctness::integer')

    op.drop_column('evaluations', 'similarity_score')
    op.drop_column('evaluations', 'expected_vs_actual_comparison')
    op.drop_column('evaluations', 'practical_application')
    op.drop_column('evaluations', 'relevance')
