"""
Loob automaatselt andmebaasiühenduse ja datasettid Supersetis.
Käivitatakse superset-init konteineris pärast 'superset init'.
Tabelid leitakse dünaamiliselt analytics-db public skeemast.
"""
import os

os.environ.setdefault("SUPERSET_CONFIG_PATH", "/app/pythonpath/superset_config.py")

from superset.app import create_app
from superset.extensions import db as superset_db

_user = os.environ["POSTGRES_USER"]
_pass = os.environ["POSTGRES_PASSWORD"]
_db   = os.environ["POSTGRES_DB"]
DB_URI = f"postgresql+psycopg2://{_user}:{_pass}@analytics-db:5432/{_db}"

app = create_app()

with app.app_context():
    from sqlalchemy import create_engine, inspect
    from superset.models.core import Database
    from superset.connectors.sqla.models import SqlaTable

    # Andmebaasiühendus
    db_entry = superset_db.session.query(Database).filter_by(database_name="Kütuse analüütikabaas").first()
    if not db_entry:
        db_entry = Database(
            database_name="Kütuse analüütikabaas",
            sqlalchemy_uri=DB_URI,
        )
        superset_db.session.add(db_entry)
        superset_db.session.commit()
        print("Andmebaasiühendus loodud.")
    else:
        print("Andmebaasiühendus on juba olemas.")

    # Leia kõik tabelid public skeemast otse andmebaasist
    try:
        engine = create_engine(DB_URI)
        inspector = inspect(engine)
        table_names = inspector.get_table_names(schema="public")
        engine.dispose()
        print(f"Leitud {len(table_names)} tabelit: {', '.join(table_names)}")
    except Exception as e:
        print(f"Andmebaas pole veel kättesaadav, datasette ei looda: {e}")
        table_names = []

    # Datasettid
    for table_name in table_names:
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
            try:
                dataset.fetch_metadata()
            except Exception:
                pass
            print(f"Dataset loodud: {table_name}")
        else:
            try:
                existing.fetch_metadata()
            except Exception:
                pass
            print(f"Dataset sünkroniseeritud: {table_name}")

    superset_db.session.commit()
    print("Kõik datasettid seadistatud.")
