import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from geoalchemy2 import Geometry

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://urbancool:urbancool@localhost:5432/urbancool",
)


class Base(DeclarativeBase):
    pass


class HeatZone(Base):
    __tablename__ = "heat_zones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(64), unique=True, nullable=False, index=True)
    city = Column(String(64), nullable=False, index=True)
    scene_id = Column(String(64), nullable=False)
    geom = Column(Geometry("POLYGON", srid=4326), nullable=False)
    mean_lst = Column(Float, nullable=False)
    ndvi = Column(Float, nullable=False)
    ndbi = Column(Float, nullable=False)
    builtup_density = Column(Float, nullable=False)
    impervious_fraction = Column(Float, nullable=False)
    water_dist_m = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    heat_class = Column(String(16), nullable=False)
    recommendation_summary = Column(Text, nullable=False)
    interventions_json = Column(Text, nullable=False)
    scene_date = Column(DateTime, nullable=True)


class CitySnapshot(Base):
    __tablename__ = "city_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String(64), nullable=False, index=True)
    scene_id = Column(String(64), nullable=False)
    scene_date = Column(DateTime, nullable=False)
    mean_lst = Column(Float, nullable=False)
    pct_low = Column(Float, nullable=False)
    pct_moderate = Column(Float, nullable=False)
    pct_high = Column(Float, nullable=False)
    pct_critical = Column(Float, nullable=False)
    critical_count = Column(Integer, nullable=False)


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
