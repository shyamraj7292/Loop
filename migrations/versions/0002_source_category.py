"""add sources.category

Adds a topical category to sources so the brief can be grouped into named,
collapsible sections (world, business, technology, sports, ...).

Revision ID: 0002_source_category
Revises: 0001_initial
Create Date: 2026-08-10
"""

from alembic import op

revision = "0002_source_category"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sources ADD COLUMN IF NOT EXISTS category VARCHAR(32);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sources_category ON sources(category);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sources_category;")
    op.execute("ALTER TABLE sources DROP COLUMN IF EXISTS category;")
