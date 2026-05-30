"""
public.ft_market
-----------------
Allikas: staging.yahoo_indikaatorid_raw (DXY, VIX, OVX)
         staging.gpr_raw (GPR päevane → nädala keskmine)
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult read, kus week_start_date > MAX(week_start_date)
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_market (
    week_start_date DATE         NOT NULL PRIMARY KEY,
    dxy             NUMERIC(8,4),
    vix             NUMERIC(8,4),
    ovx             NUMERIC(8,4),
    gpr_avg         NUMERIC(10,2),
    add_timestamp   TIMESTAMPTZ
);
"""

SELECT_SQL = """
SELECT
    date_trunc('week', y.week_date)::date   AS week_start_date,
    y.dxy                                   AS dxy,
    y.vix                                   AS vix,
    y.ovx                                   AS ovx,
    ROUND(AVG(g.gpr), 2)                    AS gpr_avg,
    y.loaded_at                             AS add_timestamp
FROM staging.yahoo_indikaatorid_raw y
LEFT JOIN staging.gpr_raw g
    ON date_trunc('week', g.gpr_date)::date = date_trunc('week', y.week_date)::date
{where_clause}
GROUP BY
    date_trunc('week', y.week_date)::date,
    y.dxy, y.vix, y.ovx, y.loaded_at
"""

INSERT_SQL = """
INSERT INTO public.ft_market
    (week_start_date, dxy, vix, ovx, gpr_avg, add_timestamp)
{select}
ON CONFLICT (week_start_date) DO NOTHING
"""


def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.ft_market LIMIT 1)")
    return cur.fetchone()[0]


def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.ft_market")
    return cur.fetchone()[0]


def run(hook):
    from contextlib import closing

    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:

                cur.execute(CREATE_TABLE_SQL)

                if _table_is_empty(cur):
                    where_clause = ""
                    print("ft_market: täida kõik read")
                else:
                    max_week = _max_week(cur)
                    where_clause = f"WHERE date_trunc('week', y.week_date)::date > '{max_week}'"
                    print(f"ft_market: inkrementaalne laadimine alates {max_week}")

                select_sql = SELECT_SQL.format(where_clause=where_clause)
                insert_sql = INSERT_SQL.format(select=select_sql)
                cur.execute(insert_sql)
                inserted = cur.rowcount
                print(f"ft_market: {inserted} rida lisatud")

    return inserted