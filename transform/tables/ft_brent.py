"""
public.ft_brent
----------------
Allikas: staging.brent_raw + staging.valuutakurss
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult read, kus week_start_date > MAX(week_start_date)
 
Teisendused:
  USD/barrel → EUR/barrel (jagatud EUR/USD kursiga)
  USD/barrel → USD/liiter (jagatud 158.987-ga)
  USD/barrel → EUR/liiter (jagatud EUR/USD kursiga ja 158.987-ga)
"""
 
BARRELS_PER_LITRE = 158.987
 
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_brent (
    week_start_date DATE         NOT NULL PRIMARY KEY,
    usd_bbl         NUMERIC(8,2),
    eur_bbl         NUMERIC(8,2),
    usd_l           NUMERIC(8,4),
    eur_l           NUMERIC(8,4),
    eur_usd_rate    NUMERIC(8,6),
    add_timestamp   TIMESTAMPTZ
);
"""
 
SELECT_SQL = """
SELECT
    date_trunc('week', b.week_date)::date           AS week_start_date,
    b.brent_usd_bbl                                 AS usd_bbl,
    ROUND(b.brent_usd_bbl / v.eur_usd, 2)           AS eur_bbl,
    ROUND(b.brent_usd_bbl / 158.987, 4)             AS usd_l,
    ROUND(b.brent_usd_bbl / 158.987 / v.eur_usd, 4) AS eur_l,
    v.eur_usd                                        AS eur_usd_rate,
    b.loaded_at                                      AS add_timestamp
FROM staging.brent_raw b
LEFT JOIN staging.valuutakurss v
    ON date_trunc('week', v.week_date)::date = date_trunc('week', b.week_date)::date
{where_clause}
"""
 
INSERT_SQL = """
INSERT INTO public.ft_brent
    (week_start_date, usd_bbl, eur_bbl, usd_l, eur_l, eur_usd_rate, add_timestamp)
{select}
ON CONFLICT (week_start_date) DO NOTHING
"""
 
 
def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.ft_brent LIMIT 1)")
    return cur.fetchone()[0]
 
 
def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.ft_brent")
    return cur.fetchone()[0]
 
 
def run(hook):
    from contextlib import closing
 
    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
 
                cur.execute(CREATE_TABLE_SQL)
 
                if _table_is_empty(cur):
                    where_clause = ""
                    print("ft_brent: täida kõik read")
                else:
                    max_week = _max_week(cur)
                    where_clause = f"WHERE date_trunc('week', b.week_date)::date > '{max_week}'"
                    print(f"ft_brent: inkrementaalne laadimine alates {max_week}")
 
                select_sql = SELECT_SQL.format(where_clause=where_clause)
                insert_sql = INSERT_SQL.format(select=select_sql)
                cur.execute(insert_sql)
                inserted = cur.rowcount
                print(f"ft_brent: {inserted} rida lisatud")
 
    return inserted