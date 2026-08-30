"""
Creates tables (if not present) and bulk-loads stations.csv / observations.csv
into PostgreSQL + PostGIS.

Run from backend/:  python3 load_data.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.core.database import engine, Base, SessionLocal
from app.models import Station, Observation  # noqa: F401 (registers tables)

DATA_DIR = Path(__file__).parent / "data"


def create_schema():
    Base.metadata.create_all(bind=engine)
    print("Schema created (or already exists).")


def load_stations(db):
    count = 0
    with open(DATA_DIR / "stations.csv", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            exists = db.get(Station, row["station_id"])
            if exists:
                continue
            station = Station(
                station_id=row["station_id"],
                name=row["name"],
                state=row["state"],
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                elevation_m=float(row["elevation_m"]),
                zone=row["zone"],
                geom=f"SRID=4326;POINT({row['lon']} {row['lat']})",
            )
            db.add(station)
            count += 1
    db.commit()
    print(f"Loaded {count} new stations.")


def load_observations(db):
    # Fast path: truncate + COPY for bulk load speed
    raw = db.connection().connection
    cur = raw.cursor()
    cur.execute("SELECT COUNT(*) FROM observations")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"observations table already has {existing} rows, skipping load "
              f"(delete rows / drop table to reload).")
        return

    with open(DATA_DIR / "observations.csv", "r") as f:
        next(f)  # skip header
        cur.copy_expert(
            """
            COPY observations (
                station_id, obs_date, temp_c, temp_max_c, temp_min_c,
                humidity_pct, rainfall_mm, wind_kmh, pressure_hpa,
                is_anomaly, anomaly_type
            )
            FROM STDIN WITH (FORMAT csv, NULL '')
            """,
            f,
        )
    raw.commit()
    cur.execute("SELECT COUNT(*) FROM observations")
    print(f"Loaded observations. Total rows: {cur.fetchone()[0]}")


def main():
    create_schema()
    db = SessionLocal()
    try:
        load_stations(db)
        load_observations(db)
    finally:
        db.close()

    # sanity check spatial index / query
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT name, ST_AsText(geom) FROM stations LIMIT 3
        """))
        for row in res:
            print(row)


if __name__ == "__main__":
    main()
