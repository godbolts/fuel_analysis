"""
public.ft_exchange_rate
------------------------
Allikas: staging.valuutakurss
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult read, kus week_start_date > MAX(week_start_date)
"""
 
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_exchange_rate (
    week_start_date DATE        NOT NULL PRIMARY KEY,
    eur_usd         NUMERIC(8,6),
    usd_eur         NUMERIC(8,6),
    add_timestamp   TIMESTAMPTZ
);
"""
 
SELECT_SQL = """
SELECT
    date_trunc('week', week_date)::date     AS week_start_date,
    eur_usd                                 AS eur_usd,
    ROUND(1.0 / eur_usd, 6)                AS usd_eur,
    loaded_at                               AS add_timestamp
FROM staging.valuutakurss
WHERE eur_usd IS NOT NULL
{where_clause}
"""
 
INSERT_SQL = """
INSERT INTO public.ft_exchange_rate
    (week_start_date, eur_usd, usd_eur, add_timestamp)
{select}
ON CONFLICT (week_start_date) DO NOTHING
"""
 
 
def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.ft_exchange_rate LIMIT 1)")
    return cur.fetchone()[0]
 
 
def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.ft_exchange_rate")
    return cur.fetchone()[0]
 
 
def run(hook):
    from contextlib import closing
 
    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
 
                cur.execute(CREATE_TABLE_SQL)
 
                if _table_is_empty(cur):
                    where_clause = ""
                    print("ft_exchange_rate: täida kõik read")
                else:
                    max_week = _max_week(cur)
                    where_clause = f"AND date_trunc('week', week_date)::date > '{max_week}'"
                    print(f"ft_exchange_rate: inkrementaalne laadimine alates {max_week}")
 
                select_sql = SELECT_SQL.format(where_clause=where_clause)
                insert_sql = INSERT_SQL.format(select=select_sql)
                cur.execute(insert_sql)
                inserted = cur.rowcount
                print(f"ft_exchange_rate: {inserted} rida lisatud")
 
    return inserted