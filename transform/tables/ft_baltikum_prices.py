"""
public.ft_baltikum_prices
--------------------------
Allikas: staging.bulletin_raw
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult uued read alates MAX(week_start_date)
  4. Lüngad nädalates   → täida lineaarse interpolatsiooniga (kahe teadaoleva punkti keskmine)
  5. is_calculated      → FALSE päris andmetel, TRUE interpoleeritud ridadel
 
Migratsioon:
  Kui tabelis puudub is_calculated veerg (vana skeem), tehakse täielik rebuild.
"""
 
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_baltikum_prices (
    week_start_date DATE        NOT NULL,
    country_code    CHAR(2)     NOT NULL,
    petrol_price    NUMERIC(6,3),
    diesel_price    NUMERIC(6,3),
    is_calculated   BOOLEAN     NOT NULL DEFAULT FALSE,
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
    FALSE                               AS is_calculated,
    loaded_at                           AS add_timestamp
FROM staging.bulletin_raw
{where_clause}
"""
 
INSERT_SQL = """
INSERT INTO public.ft_baltikum_prices
    (week_start_date, country_code, petrol_price, diesel_price, is_calculated, add_timestamp)
{select}
ON CONFLICT (week_start_date, country_code) DO NOTHING
"""
 
 
def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.ft_baltikum_prices LIMIT 1)")
    return cur.fetchone()[0]
 
 
def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.ft_baltikum_prices")
    return cur.fetchone()[0]
 
 
def _needs_rebuild(cur) -> bool:
    """Kontrolli kas is_calculated veerg on olemas — kui mitte, vajab täielikku rebuildi."""
    cur.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'ft_baltikum_prices'
              AND column_name  = 'is_calculated'
        )
    """)
    return not cur.fetchone()[0]
 
 
def _fill_gaps(cur):
    """
    Leia lüngad dm_date_aggregation ja ft_baltikum_prices vahel iga riigi kohta.
    Täida lineaarse interpolatsiooniga: puuduva nädala väärtus = keskmine kahest
    lähimast teadaolevast punktist (eelmine + järgmine).
    """
    # Leia kõik riigid
    cur.execute("SELECT DISTINCT country_code FROM public.ft_baltikum_prices")
    countries = [row[0] for row in cur.fetchall()]
 
    total_filled = 0
 
    for country in countries:
        # Leia puuduvad nädalad: dm_date_aggregation nädalad mis pole ft tabelis
        cur.execute("""
            SELECT d.week_start_date
            FROM public.dm_date_aggregation d
            WHERE d.week_start_date BETWEEN (
                SELECT MIN(week_start_date) FROM public.ft_baltikum_prices WHERE country_code = %s
            ) AND (
                SELECT MAX(week_start_date) FROM public.ft_baltikum_prices WHERE country_code = %s
            )
            AND NOT EXISTS (
                SELECT 1 FROM public.ft_baltikum_prices f
                WHERE f.week_start_date = d.week_start_date
                  AND f.country_code = %s
            )
            ORDER BY d.week_start_date
        """, (country, country, country))
 
        missing_weeks = [row[0] for row in cur.fetchall()]
 
        if not missing_weeks:
            continue
 
        print(f"  {country}: {len(missing_weeks)} puuduvat nädalat, interpoleerin...")
 
        for missing_date in missing_weeks:
            # Leia eelmine teadaolev punkt
            cur.execute("""
                SELECT week_start_date, petrol_price, diesel_price
                FROM public.ft_baltikum_prices
                WHERE country_code = %s AND week_start_date < %s AND is_calculated = FALSE
                ORDER BY week_start_date DESC
                LIMIT 1
            """, (country, missing_date))
            prev = cur.fetchone()
 
            # Leia järgmine teadaolev punkt
            cur.execute("""
                SELECT week_start_date, petrol_price, diesel_price
                FROM public.ft_baltikum_prices
                WHERE country_code = %s AND week_start_date > %s AND is_calculated = FALSE
                ORDER BY week_start_date ASC
                LIMIT 1
            """, (country, missing_date))
            nxt = cur.fetchone()
 
            if prev is None or nxt is None:
                # Ei saa interpoleerida kui puudub üks pool
                print(f"    {missing_date}: ei saa interpoleerida (puudub {'eelmine' if prev is None else 'järgmine'} punkt)")
                continue
 
            prev_date, prev_petrol, prev_diesel = prev
            next_date, next_petrol, next_diesel = nxt
 
            # Lineaarne interpolatsioon ajalise kauguse järgi
            total_days = (next_date - prev_date).days
            missing_days = (missing_date - prev_date).days
            ratio = missing_days / total_days if total_days > 0 else 0.5
 
            def interp(a, b):
                if a is None or b is None:
                    return None
                return round(float(a) + ratio * (float(b) - float(a)), 3)
 
            petrol_interp = interp(prev_petrol, next_petrol)
            diesel_interp = interp(prev_diesel, next_diesel)
 
            cur.execute("""
                INSERT INTO public.ft_baltikum_prices
                    (week_start_date, country_code, petrol_price, diesel_price, is_calculated, add_timestamp)
                VALUES (%s, %s, %s, %s, TRUE, NOW())
                ON CONFLICT (week_start_date, country_code) DO NOTHING
            """, (missing_date, country, petrol_interp, diesel_interp))
 
            total_filled += cur.rowcount
 
    print(f"  Interpoleeritud kokku: {total_filled} rida")
    return total_filled
 
 
def run(hook):
    from contextlib import closing
 
    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
 
                # Migratsioon: kui vana skeem ilma is_calculated, tee täielik rebuild
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'ft_baltikum_prices'
                    )
                """)
                table_exists = cur.fetchone()[0]
 
                if table_exists and _needs_rebuild(cur):
                    print("ft_baltikum_prices: vana skeem tuvastatud (puudub is_calculated) → täielik rebuild")
                    cur.execute("DROP TABLE public.ft_baltikum_prices")
                    table_exists = False
 
                cur.execute(CREATE_TABLE_SQL)
 
                # Lae päris andmed staging-ist
                if not table_exists or _table_is_empty(cur):
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
                print(f"ft_baltikum_prices: {inserted} päris rida lisatud")
 
                # Täida lüngad interpolatsiooniga
                _fill_gaps(cur)
 
    return inserted