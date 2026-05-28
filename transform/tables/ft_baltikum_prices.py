"""
public.ft_baltikum_prices
--------------------------
Allikas: staging.bulletin_raw
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult read, kus week_start_date > MAX(week_start_date)
"""
 
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_baltikum_prices (
    week_start_date DATE        NOT NULL,
    country_code    CHAR(2)     NOT NULL,
    petrol_price    NUMERIC(6,3),
    diesel_price    NUMERIC(6,3),
    add_timestamp   TIMESTAMPTZ,
    PRIMARY KEY (week_start_date, country_code)
);
"""
 
SELECT_SQL = """
SELECT
    date_trunc('week', week_date)::date AS week_start_date,
    country                             AS country_code,
    ROUND(euro95_eur_kl / 1000.0, 3)   AS petrol_price,
    ROUND(diesel_eur_kl / 1000.0, 3)   AS diesel_price,
    loaded_at                           AS add_timestamp
FROM staging.bulletin_raw
{where_clause}
"""
 
INSERT_SQL = """
INSERT INTO public.ft_baltikum_prices
    (week_start_date, country_code, petrol_price, diesel_price, add_timestamp)
{select}
ON CONFLICT (week_start_date, country_code) DO NOTHING
"""
 
 
def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.ft_baltikum_prices LIMIT 1)")
    return cur.fetchone()[0]
 
 
def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.ft_baltikum_prices")
    return cur.fetchone()[0]
 
 
def run(hook):
    from contextlib import closing
 
    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
 
                cur.execute(CREATE_TABLE_SQL)
 
                if _table_is_empty(cur):
                    where_clause = ""
                    print("ft_baltikum_prices: täida kõik read")
                else:
                    max_week = _max_week(cur)
                    where_clause = f"WHERE date_trunc('week', week_date)::date > '{max_week}'"
                    print(f"ft_baltikum_prices: inkrementaalne laadimine alates {max_week}")
 
                select_sql = SELECT_SQL.format(where_clause=where_clause)
                insert_sql = INSERT_SQL.format(select=select_sql)
                cur.execute(insert_sql)
                inserted = cur.rowcount
                print(f"ft_baltikum_prices: {inserted} rida lisatud")
 
    return inserted