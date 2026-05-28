"""
public.ft_usa_prices
---------------------
Allikas: staging.eia_spothinnad_raw + staging.valuutakurss
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult read, kus week_start_date > MAX(week_start_date)
 
Teisendused:
  USD/gallon → USD/liiter (1 gallon = 3.78541 l)
  USD/liiter → EUR/liiter (jagatud EUR/USD kursiga)
"""
 
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_usa_prices (
    week_start_date DATE        NOT NULL,
    country_code    CHAR(2)     NOT NULL DEFAULT 'US',
    petrol_usd_l    NUMERIC(6,4),
    diesel_usd_l    NUMERIC(6,4),
    petrol_eur_l    NUMERIC(6,4),
    diesel_eur_l    NUMERIC(6,4),
    add_timestamp   TIMESTAMPTZ,
    PRIMARY KEY (week_start_date, country_code)
);
"""
 
SELECT_SQL = """
SELECT
    date_trunc('week', s.week_date)::date           AS week_start_date,
    'US'                                             AS country_code,
    ROUND(s.bensiin95_usd_gal / 3.78541, 4)         AS petrol_usd_l,
    ROUND(s.diisel_usd_gal    / 3.78541, 4)         AS diesel_usd_l,
    ROUND((s.bensiin95_usd_gal / 3.78541) / v.eur_usd, 4) AS petrol_eur_l,
    ROUND((s.diisel_usd_gal    / 3.78541) / v.eur_usd, 4) AS diesel_eur_l,
    s.loaded_at                                      AS add_timestamp
FROM staging.eia_spothinnad_raw s
LEFT JOIN staging.valuutakurss v
    ON date_trunc('week', v.week_date)::date = date_trunc('week', s.week_date)::date
{where_clause}
"""
 
INSERT_SQL = """
INSERT INTO public.ft_usa_prices
    (week_start_date, country_code, petrol_usd_l, diesel_usd_l,
     petrol_eur_l, diesel_eur_l, add_timestamp)
{select}
ON CONFLICT (week_start_date, country_code) DO NOTHING
"""
 
 
def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.ft_usa_prices LIMIT 1)")
    return cur.fetchone()[0]
 
 
def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.ft_usa_prices")
    return cur.fetchone()[0]
 
 
def run(hook):
    from contextlib import closing
 
    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
 
                cur.execute(CREATE_TABLE_SQL)
 
                if _table_is_empty(cur):
                    where_clause = ""
                    print("ft_usa_prices: täida kõik read")
                else:
                    max_week = _max_week(cur)
                    where_clause = f"WHERE date_trunc('week', s.week_date)::date > '{max_week}'"
                    print(f"ft_usa_prices: inkrementaalne laadimine alates {max_week}")
 
                select_sql = SELECT_SQL.format(where_clause=where_clause)
                insert_sql = INSERT_SQL.format(select=select_sql)
                cur.execute(insert_sql)
                inserted = cur.rowcount
                print(f"ft_usa_prices: {inserted} rida lisatud")
 
    return inserted