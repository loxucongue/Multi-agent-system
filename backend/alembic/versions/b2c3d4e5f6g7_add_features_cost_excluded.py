"""add features and cost_excluded to routes

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("routes")}
    indexes = {index["name"] for index in inspector.get_indexes("routes")}

    if "features" not in columns:
        op.add_column(
            "routes",
            sa.Column("features", sa.Text(), nullable=True, comment="Route feature tags text"),
        )
    if "cost_excluded" not in columns:
        op.add_column(
            "routes",
            sa.Column("cost_excluded", sa.Text(), nullable=True, comment="Cost excluded details"),
        )

    if "uq_routes_doc_url" not in indexes:
        duplicate_urls = bind.execute(
            sa.text(
                """
                SELECT doc_url
                FROM routes
                WHERE doc_url IS NOT NULL AND doc_url <> ''
                GROUP BY doc_url
                HAVING COUNT(*) > 1
                """
            ),
        ).fetchall()

        for row in duplicate_urls:
            doc_url = row[0]
            duplicated_rows = bind.execute(
                sa.text(
                    """
                    SELECT id
                    FROM routes
                    WHERE doc_url = :doc_url
                    ORDER BY id ASC
                    """
                ),
                {"doc_url": doc_url},
            ).fetchall()
            for dup in duplicated_rows[1:]:
                route_id = dup[0]
                bind.execute(
                    sa.text(
                        """
                        UPDATE routes
                        SET doc_url = :new_doc_url
                        WHERE id = :route_id
                        """
                    ),
                    {"new_doc_url": f"{doc_url}#dup-{route_id}", "route_id": route_id},
                )

        op.create_index("uq_routes_doc_url", "routes", ["doc_url"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("routes")}
    indexes = {index["name"] for index in inspector.get_indexes("routes")}

    if "uq_routes_doc_url" in indexes:
        op.drop_index("uq_routes_doc_url", table_name="routes")
    if "cost_excluded" in columns:
        op.drop_column("routes", "cost_excluded")
    if "features" in columns:
        op.drop_column("routes", "features")