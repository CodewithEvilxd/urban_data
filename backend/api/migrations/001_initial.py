"""Alembic migration revision placeholder — schema created via api/seed_db.py Base.metadata.create_all"""

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "heat_zones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("zone_id", sa.String(64), nullable=False, unique=True),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("scene_id", sa.String(64), nullable=False),
        sa.Column("geom", Geometry("POLYGON", srid=4326), nullable=False),
        sa.Column("mean_lst", sa.Float(), nullable=False),
        sa.Column("ndvi", sa.Float(), nullable=False),
        sa.Column("ndbi", sa.Float(), nullable=False),
        sa.Column("builtup_density", sa.Float(), nullable=False),
        sa.Column("impervious_fraction", sa.Float(), nullable=False),
        sa.Column("water_dist_m", sa.Float(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("heat_class", sa.String(16), nullable=False),
        sa.Column("recommendation_summary", sa.Text(), nullable=False),
        sa.Column("interventions_json", sa.Text(), nullable=False),
        sa.Column("scene_date", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_heat_zones_city", "heat_zones", ["city"])
    op.create_index("ix_heat_zones_zone_id", "heat_zones", ["zone_id"])

    op.create_table(
        "city_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("scene_id", sa.String(64), nullable=False),
        sa.Column("scene_date", sa.DateTime(), nullable=False),
        sa.Column("mean_lst", sa.Float(), nullable=False),
        sa.Column("pct_low", sa.Float(), nullable=False),
        sa.Column("pct_moderate", sa.Float(), nullable=False),
        sa.Column("pct_high", sa.Float(), nullable=False),
        sa.Column("pct_critical", sa.Float(), nullable=False),
        sa.Column("critical_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_city_snapshots_city", "city_snapshots", ["city"])


def downgrade():
    op.drop_table("city_snapshots")
    op.drop_table("heat_zones")
