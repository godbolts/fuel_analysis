"""
Baltikumi kutusehinnad — Airflow ingest pipeline

Allikad:
  - EU Weekly Oil Bulletin (EE, LV, LT)  → staging.bulletin_raw
  - Yahoo Finance Brent                   → staging.brent_raw
  - EIA spothinnad (bensiin, diisel)      → staging.eia_spothinnad_raw
  - Yahoo Finance EUR/USD                 → staging.valuutakurss
  - Yahoo Finance DXY, VIX, OVX          → staging.yahoo_indikaatorid_raw
  - GPR paevane indeks                    → staging.gpr_raw
  - EIA naftavarud tase                   → staging.eia_varud_raw

Ajakava: iga neljapaev kell 08:00
Idempotentne: ON CONFLICT DO UPDATE
"""

from datetime import timedelta

import pendulum

from airflow.sdk import dag, task

BULLETIN_URL = "https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx"
EIA_SPOT_URL = "https://www.eia.gov/dnav/pet/xls/PET_PRI_SPT_S1_W.xls"
EIA_VARUD_URL = "https://www.eia.gov/dnav/pet/hist_xls/WCRSTUS1w.xls"
GPR_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
START_YEAR = 2022


@dag(
    dag_id="kutuse_hind_pipeline",
    schedule="0 8 * * 5",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    tags=["kutus", "baltikum"],
)
def kutuse_hind_pipeline():

    # ── 1. EU BULLETIN ────────────────────────────────────────────────────

    @task(retries=3, retry_delay=timedelta(minutes=5))
    def extract_bulletin() -> list[dict]:
        """EU Weekly Oil Bulletin → EE/LV/LT Euro95 ja Diesel €/l."""
        from io import BytesIO
        import pandas as pd
        import requests
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        last = PostgresHook(postgres_conn_id="analytics_db").get_first(
            "SELECT MAX(week_date) FROM staging.bulletin_raw"
        )[0]
        start = pd.Timestamp(last) + pd.Timedelta(days=1) if last else pd.Timestamp(f"{START_YEAR}-01-01")

        resp = requests.get(BULLETIN_URL, timeout=90)
        resp.raise_for_status()
        df_raw = pd.read_excel(BytesIO(resp.content), sheet_name="Prices with taxes", header=None)
        header_row = df_raw.iloc[0, :].astype(str)
        data = df_raw.iloc[3:, :].copy()
        data["date"] = pd.to_datetime(data.iloc[:, 0], errors="coerce")
        data = data[data["date"] >= start].reset_index(drop=True)

        def find_cols(prefix):
            return [i for i, v in enumerate(header_row) if v.startswith(prefix)]

        rows = []
        for country, prefix in [("EE", "EE_"), ("LV", "LV_"), ("LT", "LT_")]:
            cols = find_cols(prefix)
            col_95, col_diesel = cols[1], cols[2]
            for _, row in data.iterrows():
                try:
                    euro95 = round(float(row.iloc[col_95]), 2)
                except (ValueError, TypeError):
                    euro95 = None
                try:
                    diesel = round(float(row.iloc[col_diesel]), 2)
                except (ValueError, TypeError):
                    diesel = None
                rows.append({"week_date": row["date"].strftime("%Y-%m-%d"),
                             "country": country, "euro95_eur_kl": euro95, "diesel_eur_kl": diesel})
        print(f"Bulletin: {len(rows)} rida")
        return rows

    @task
    def load_staging_bulletin(rows: list[dict]) -> int:
        from contextlib import closing
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        hook = PostgresHook(postgres_conn_id="analytics_db")
        inserted = 0
        with closing(hook.get_conn()) as conn, conn, conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """INSERT INTO staging.bulletin_raw
                           (week_date, country, euro95_eur_kl, diesel_eur_kl, loaded_at)
                       VALUES (%s, %s, %s, %s, NOW())
                       ON CONFLICT (week_date, country) DO NOTHING""",
                    (r["week_date"], r["country"], r["euro95_eur_kl"], r["diesel_eur_kl"]),
                )
                inserted += cur.rowcount
        print(f"bulletin_raw: {inserted} uut rida lisatud ({len(rows) - inserted} olemas)")
        return inserted

    # ── 2a. BRENT: Yahoo Finance Brent crude ─────────────────────────────

    @task(retries=3, retry_delay=timedelta(minutes=5))
    def extract_brent() -> list[dict]:
        """Yahoo Finance: Brent crude oil iganadalane sulgemishind USD/bbl."""
        import pandas as pd
        import requests
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        last = PostgresHook(postgres_conn_id="analytics_db").get_first(
            "SELECT MAX(week_date) FROM staging.brent_raw"
        )[0]
        start = pd.Timestamp(last) + pd.Timedelta(days=1) if last else pd.Timestamp(f"{START_YEAR}-01-01")
        today = pd.Timestamp.now().normalize()
        this_monday = today - pd.Timedelta(days=today.weekday())
        if start >= this_monday:
            print("Brent: andmed on ajakohased, midagi uut pole")
            return []
        period1 = int(start.timestamp())
        period2 = int(pd.Timestamp.now().timestamp())

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/BZ%3DF?interval=1wk&period1={period1}&period2={period2}"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        d = r.json()["chart"]["result"][0]
        dates = pd.to_datetime(d["timestamp"], unit="s").normalize()
        closes = d["indicators"]["quote"][0]["close"]
        s = pd.Series(closes, index=dates, name="brent_usd_bbl").dropna()
        today = pd.Timestamp.now().normalize()
        this_monday = today - pd.Timedelta(days=today.weekday())
        s = s[s.index < this_monday]
        rows = [{"week_date": d.strftime("%Y-%m-%d"), "brent_usd_bbl": round(float(v), 2)}
                for d, v in s.items()]
        print(f"Brent: {len(rows)} uut rida (alates {start.date()})")
        return rows

    @task
    def load_staging_brent(rows: list[dict]) -> int:
        from contextlib import closing
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        hook = PostgresHook(postgres_conn_id="analytics_db")
        inserted = 0
        with closing(hook.get_conn()) as conn, conn, conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """INSERT INTO staging.brent_raw (week_date, brent_usd_bbl, loaded_at)
                       VALUES (%s, %s, NOW())
                       ON CONFLICT (week_date) DO NOTHING""",
                    (r["week_date"], r["brent_usd_bbl"]),
                )
                inserted += cur.rowcount
        print(f"brent_raw: {inserted} uut rida lisatud ({len(rows) - inserted} olemas)")
        return inserted

    # ── 2b. EIA SPOTHINNAD: bensiin + diisel ─────────────────────────────

    @task(retries=3, retry_delay=timedelta(minutes=5))
    def extract_eia_spothinnad() -> list[dict]:
        """EIA US Gulf Coast spothinnad: bensiin ja diisel USD/gal (reede kuupaev)."""
        from io import BytesIO
        import pandas as pd
        import requests
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        last = PostgresHook(postgres_conn_id="analytics_db").get_first(
            "SELECT MAX(week_date) FROM staging.eia_spothinnad_raw"
        )[0]
        start = pd.Timestamp(last) + pd.Timedelta(days=1) if last else pd.Timestamp(f"{START_YEAR}-01-01")

        r = requests.get(EIA_SPOT_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        xl = pd.ExcelFile(BytesIO(r.content), engine="xlrd")

        def parse_sheet(sheet, col):
            df = xl.parse(sheet, header=2, index_col=0, parse_dates=True)
            return df.iloc[:, col - 1]

        bensiin = parse_sheet("Data 2", 2)
        diisel = parse_sheet("Data 5", 2)
        df = pd.DataFrame({"bensiin95_usd_gal": bensiin, "diisel_usd_gal": diisel})
        df = df[df.index >= start]
        rows = []
        for d, row in df.iterrows():
            rows.append({
                "week_date": d.strftime("%Y-%m-%d"),
                "bensiin95_usd_gal": round(float(row["bensiin95_usd_gal"]), 4) if pd.notna(row["bensiin95_usd_gal"]) else None,
                "diisel_usd_gal": round(float(row["diisel_usd_gal"]), 4) if pd.notna(row["diisel_usd_gal"]) else None,
            })
        print(f"EIA spothinnad: {len(rows)} rida")
        return rows

    @task
    def load_staging_eia_spothinnad(rows: list[dict]) -> int:
        from contextlib import closing
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        hook = PostgresHook(postgres_conn_id="analytics_db")
        inserted = 0
        with closing(hook.get_conn()) as conn, conn, conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """INSERT INTO staging.eia_spothinnad_raw
                           (week_date, bensiin95_usd_gal, diisel_usd_gal, loaded_at)
                       VALUES (%s, %s, %s, NOW())
                       ON CONFLICT (week_date) DO NOTHING""",
                    (r["week_date"], r["bensiin95_usd_gal"], r["diisel_usd_gal"]),
                )
                inserted += cur.rowcount
        print(f"eia_spothinnad_raw: {inserted} uut rida lisatud ({len(rows) - inserted} olemas)")
        return inserted

    # ── 3. EUR/USD VALUUTAKURSS ───────────────────────────────────────────

    @task(retries=3, retry_delay=timedelta(minutes=5))
    def extract_valuutakurss() -> list[dict]:
        """Yahoo Finance: EUR/USD iganadalane sulgemiskurss."""
        import pandas as pd
        import requests
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        last = PostgresHook(postgres_conn_id="analytics_db").get_first(
            "SELECT MAX(week_date) FROM staging.valuutakurss"
        )[0]
        start = pd.Timestamp(last) + pd.Timedelta(days=1) if last else pd.Timestamp(f"{START_YEAR}-01-01")
        today = pd.Timestamp.now().normalize()
        this_monday = today - pd.Timedelta(days=today.weekday())
        if start >= this_monday:
            print("EUR/USD: andmed on ajakohased, midagi uut pole")
            return []
        period1 = int(start.timestamp())
        period2 = int(pd.Timestamp.now().timestamp())

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/EURUSD%3DX?interval=1wk&period1={period1}&period2={period2}"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        d = r.json()["chart"]["result"][0]
        dates = pd.to_datetime(d["timestamp"], unit="s").normalize()
        closes = d["indicators"]["quote"][0]["close"]
        s = pd.Series(closes, index=dates, name="eur_usd")
        rows = [{"week_date": d.strftime("%Y-%m-%d"),
                 "eur_usd": round(float(v), 5) if pd.notna(v) else None}
                for d, v in s.items()]
        print(f"EUR/USD: {len(rows)} uut rida (alates {start.date()})")
        return rows

    @task
    def load_staging_valuutakurss(rows: list[dict]) -> int:
        from contextlib import closing
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        hook = PostgresHook(postgres_conn_id="analytics_db")
        inserted = 0
        with closing(hook.get_conn()) as conn, conn, conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """INSERT INTO staging.valuutakurss
                           (week_date, eur_usd, loaded_at)
                       VALUES (%s, %s, NOW())
                       ON CONFLICT (week_date) DO NOTHING""",
                    (r["week_date"], r["eur_usd"]),
                )
                inserted += cur.rowcount
        print(f"valuutakurss: {inserted} uut rida lisatud ({len(rows) - inserted} olemas)")
        return inserted

    # ── 4. YAHOO INDIKAATORID (DXY, VIX, OVX) ────────────────────────────

    @task(retries=3, retry_delay=timedelta(minutes=5))
    def extract_yahoo_indikaatorid() -> list[dict]:
        """DXY, VIX, OVX Yahoo Finance – toorandmed (nädala close)."""
        import pandas as pd
        import requests
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        last = PostgresHook(postgres_conn_id="analytics_db").get_first(
            "SELECT MAX(week_date) FROM staging.yahoo_indikaatorid_raw"
        )[0]
        start = pd.Timestamp(last) + pd.Timedelta(days=1) if last else pd.Timestamp(f"{START_YEAR}-01-01")
        today = pd.Timestamp.now().normalize()
        this_monday = today - pd.Timedelta(days=today.weekday())
        if start >= this_monday:
            print("Yahoo indikaatorid: andmed on ajakohased, midagi uut pole")
            return []
        period1 = int(start.timestamp())
        period2 = int(pd.Timestamp.now().timestamp())

        def fetch_yahoo(ticker, name):
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1wk&period1={period1}&period2={period2}"
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            d = r.json()["chart"]["result"][0]
            dates = pd.to_datetime(d["timestamp"], unit="s").normalize()
            closes = d["indicators"]["quote"][0]["close"]
            s = pd.Series(closes, index=dates, name=name).dropna()
            return s

        dxy = fetch_yahoo("DX-Y.NYB", "dxy")
        vix = fetch_yahoo("%5EVIX", "vix")
        ovx = fetch_yahoo("%5EOVX", "ovx")

        today = pd.Timestamp.now().normalize()
        this_monday = today - pd.Timedelta(days=today.weekday())
        df = pd.DataFrame({"dxy": dxy, "vix": vix, "ovx": ovx})
        df = df[(df.index >= start) & (df.index < this_monday)]

        rows = []
        for d, r in df.iterrows():
            rows.append({
                "week_date": d.strftime("%Y-%m-%d"),
                "dxy": round(float(r["dxy"]), 4) if pd.notna(r["dxy"]) else None,
                "vix": round(float(r["vix"]), 4) if pd.notna(r["vix"]) else None,
                "ovx": round(float(r["ovx"]), 4) if pd.notna(r["ovx"]) else None,
            })
        print(f"Yahoo indikaatorid: {len(rows)} rida")
        return rows

    @task
    def load_staging_yahoo_indikaatorid(rows: list[dict]) -> int:
        from contextlib import closing
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        hook = PostgresHook(postgres_conn_id="analytics_db")
        inserted = 0
        with closing(hook.get_conn()) as conn, conn, conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """INSERT INTO staging.yahoo_indikaatorid_raw
                           (week_date, dxy, vix, ovx, loaded_at)
                       VALUES (%s, %s, %s, %s, NOW())
                       ON CONFLICT (week_date) DO NOTHING""",
                    (r["week_date"], r["dxy"], r["vix"], r["ovx"]),
                )
                inserted += cur.rowcount
        print(f"yahoo_indikaatorid_raw: {inserted} uut rida ({len(rows) - inserted} olemas)")
        return inserted

    # ── 5. GPR (geopoliitilise riski indeks) ─────────────────────────────

    @task(retries=3, retry_delay=timedelta(minutes=5))
    def extract_gpr() -> list[dict]:
        """GPR – päeva toorandmed (GPRD veerg), agregeerimine nädalaks SQL-kihis."""
        from io import BytesIO
        import pandas as pd
        import requests
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        last = PostgresHook(postgres_conn_id="analytics_db").get_first(
            "SELECT MAX(gpr_date) FROM staging.gpr_raw"
        )[0]
        start = pd.Timestamp(last) + pd.Timedelta(days=1) if last else pd.Timestamp(f"{START_YEAR}-01-01")

        r = requests.get(GPR_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        gpr_df = pd.read_excel(BytesIO(r.content))
        date_col = "date" if "date" in gpr_df.columns else gpr_df.columns[0]
        gpr_col = [c for c in gpr_df.columns if "GPR" in str(c).upper()
                   and "THREAT" not in str(c).upper() and "ACT" not in str(c).upper()
                   and "MA" not in str(c).upper()][0]
        gpr_df = gpr_df[[date_col, gpr_col]].copy()
        gpr_df.columns = ["gpr_date", "gpr"]
        gpr_df["gpr_date"] = pd.to_datetime(gpr_df["gpr_date"], errors="coerce")
        gpr_df["gpr"] = pd.to_numeric(gpr_df["gpr"], errors="coerce")
        gpr_df = gpr_df.dropna()
        gpr_df = gpr_df[gpr_df["gpr_date"] >= start]

        rows = []
        for _, row in gpr_df.iterrows():
            rows.append({
                "gpr_date": row["gpr_date"].strftime("%Y-%m-%d"),
                "gpr": round(float(row["gpr"]), 2),
            })
        print(f"GPR: {len(rows)} rida")
        return rows

    @task
    def load_staging_gpr(rows: list[dict]) -> int:
        from contextlib import closing
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        hook = PostgresHook(postgres_conn_id="analytics_db")
        inserted = 0
        with closing(hook.get_conn()) as conn, conn, conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """INSERT INTO staging.gpr_raw (gpr_date, gpr, loaded_at)
                       VALUES (%s, %s, NOW())
                       ON CONFLICT (gpr_date) DO NOTHING""",
                    (r["gpr_date"], r["gpr"]),
                )
                inserted += cur.rowcount
        print(f"gpr_raw: {inserted} uut rida ({len(rows) - inserted} olemas)")
        return inserted

    # ── 6. EIA NAFTAVARUD ─────────────────────────────────────────────────

    @task(retries=3, retry_delay=timedelta(minutes=5))
    def extract_eia_varud() -> list[dict]:
        """EIA US naftavarud – nädala tase (tuhat barrelit), delta SQL-kihis."""
        from io import BytesIO
        import pandas as pd
        import requests
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        last = PostgresHook(postgres_conn_id="analytics_db").get_first(
            "SELECT MAX(varud_date) FROM staging.eia_varud_raw"
        )[0]
        start = pd.Timestamp(last) + pd.Timedelta(days=1) if last else pd.Timestamp(f"{START_YEAR}-01-01")

        r = requests.get(EIA_VARUD_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        df = pd.read_excel(BytesIO(r.content), sheet_name="Data 1", header=2, index_col=0)
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df.dropna()
        varud = df.iloc[:, 0]
        varud = varud[varud.index >= start]

        rows = []
        for d, v in varud.items():
            rows.append({
                "varud_date": d.strftime("%Y-%m-%d"),
                "eia_varud": round(float(v), 0),
            })
        print(f"EIA varud: {len(rows)} rida")
        return rows

    @task
    def load_staging_eia_varud(rows: list[dict]) -> int:
        from contextlib import closing
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        hook = PostgresHook(postgres_conn_id="analytics_db")
        inserted = 0
        with closing(hook.get_conn()) as conn, conn, conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """INSERT INTO staging.eia_varud_raw (varud_date, eia_varud, loaded_at)
                       VALUES (%s, %s, NOW())
                       ON CONFLICT (varud_date) DO NOTHING""",
                    (r["varud_date"], r["eia_varud"]),
                )
                inserted += cur.rowcount
        print(f"eia_varud_raw: {inserted} uut rida ({len(rows) - inserted} olemas)")
        return inserted

    # ── Voog ──────────────────────────────────────────────────────────────
    load_staging_bulletin(extract_bulletin())
    load_staging_brent(extract_brent())
    load_staging_eia_spothinnad(extract_eia_spothinnad())
    load_staging_valuutakurss(extract_valuutakurss())
    load_staging_yahoo_indikaatorid(extract_yahoo_indikaatorid())
    load_staging_gpr(extract_gpr())
    load_staging_eia_varud(extract_eia_varud())


kutuse_hind_pipeline()
