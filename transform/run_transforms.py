"""
transform/run_transforms.py
"""

import importlib.util
import sys
import os

from airflow.providers.postgres.hooks.postgres import PostgresHook


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_all():
    hook = PostgresHook(postgres_conn_id="analytics_db")

    base = "/opt/airflow/transform/tables"
    print(f"DEBUG: failid kaustas: {os.listdir(base)}") 
    transformations = [
        load_module("dm_country", os.path.join(base, "dm_country.py")),
        load_module("ft_usa_prices", os.path.join(base, "ft_usa_prices.py")),
        load_module("ft_exchange_rate", os.path.join(base, "ft_exchange_rate.py")),
        load_module("ft_baltikum_prices", os.path.join(base, "ft_baltikum_prices.py")),
    ]

    for transformer in transformations:
        name = transformer.__name__
        print(f"\n>>> {name}")
        try:
            inserted = transformer.run(hook)
            print(f"<<< {name}: OK ({inserted} rida)")
        except Exception as e:
            print(f"<<< {name}: VIGA — {e}")
            raise


if __name__ == "__main__":
    run_all()