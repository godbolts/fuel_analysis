"""
Loob automaatselt andmebaasiühenduse ja datasettid Supersetis.
Käivitatakse superset-init konteineris pärast 'superset init'.
"""
import os

os.environ.setdefault("SUPERSET_CONFIG_PATH", "/app/pythonpath/superset_config.py")

from superset.app import create_app
from superset.extensions import db as superset_db

MART_TABLES = [
    "ft_baltikum_prices",
    "ft_brent",
    "ft_usa_prices",
    "ft_market",
    "ft_exchange_rate",
    "dm_country",
    "dm_date_aggregation",
    "ft_price_forecast",
]

app = create_app()

with app.app_context():
    from superset.models.core import Database
    from superset.connectors.sqla.models import SqlaTable

    # Andmebaasiühendus
    db_entry = superset_db.session.query(Database).filter_by(database_name="Kütuse analüütikabaas").first()
    if not db_entry:
        db_entry = Database(
            database_name="Kütuse analüütikabaas",
            sqlalchemy_uri="postgresql+psycopg2://bensiin:bensiinikanister@analytics-db:5432/bensiin",
        )
        superset_db.session.add(db_entry)
        superset_db.session.commit()
        print("Andmebaasiühendus loodud.")
    else:
        print("Andmebaasiühendus on juba olemas.")

    # Datasettid
    for table_name in MART_TABLES:
        existing = superset_db.session.query(SqlaTable).filter_by(
            table_name=table_name,
            database_id=db_entry.id,
        ).first()
        if not existing:
            dataset = SqlaTable(
                table_name=table_name,
                schema="public",
                database_id=db_entry.id,
            )
            superset_db.session.add(dataset)
            superset_db.session.flush()
            dataset.fetch_metadata()
            print(f"Dataset loodud: {table_name}")
        else:
            existing.fetch_metadata()
            print(f"Dataset sünkroniseeritud: {table_name}")

    superset_db.session.commit()
    print("Kõik datasettid seadistatud.")
