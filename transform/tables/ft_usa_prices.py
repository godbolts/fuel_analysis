"""
public.ft_usa_prices
---------------------
Allikas: staging.eia_spothinnad_raw + staging.valuutakurss + staging.eia_varud_raw
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult read, kus week_start_date > MAX(week_start_date)
  4. Lüngad nädalates   → täida lineaarse interpolatsiooniga
  5. is_calculated      → FALSE päris andmetel, TRUE interpoleeritud ridadel

Teisendused:
  USD/gallon → USD/liiter (1 gallon = 3.78541 l)
  USD/liiter → EUR/liiter (jagatud EUR/USD kursiga)
  eia_varud: tase (tuh. bbl) + delta eelmisest nädalast (LAG)

Migratsioon:
  - ADD COLUMN IF NOT EXISTS lisab eia_varud veerud vaikselt
  - Kui puudub is_calculated veerg, tehakse täielik rebuild
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_usa_prices (
    week_start_date    DATE        NOT NULL,
    country_code       CHAR(2)     NOT NULL DEFAULT 'US',
    petrol_usd_l       NUMERIC(6,4),
    diesel_usd_l       NUMERIC(6,4),
    petrol_eur_l       NUMERIC(6,4),
    diesel_eur_l       NUMERIC(6,4),
    eia_varud_tuh_bbl  NUMERIC(12,0),
    eia_varud_delta    NUMERIC(12,0),
    is_calculated      BOOLEAN     NOT NULL DEFAULT FALSE,
    add_timestamp      TIMESTAMPTZ,
    PRIMARY KEY (week_start_date, country_code)
);
"""

ALTER_TABLE_SQL = """
ALTER TABLE public.ft_usa_prices
    ADD COLUMN IF NOT EXISTS eia_varud_tuh_bbl NUMERIC(12,0),
    ADD COLUMN IF NOT EXISTS eia_varud_delta   NUMERIC(12,0),
    ADD COLUMN IF NOT EXISTS is_calculated     BOOLEAN NOT NULL DEFAULT FALSE;
"""

SELECT_SQL = """
WITH varud AS (
    SELECT
        date_trunc('week', varud_date)::date            AS week_start_date,
        eia_varud                                        AS eia_varud_tuh_bbl,
        eia_varud - LAG(eia_varud) OVER (
            ORDER BY date_trunc('week', varud_date)::date
        )                                                AS eia_varud_delta
    FROM staging.eia_varud_raw
)
SELECT
    date_trunc('week', s.week_date)::date                       AS week_start_date,
    'US'                                                         AS country_code,
    ROUND(s.bensiin95_usd_gal / 3.78541, 4)                     AS petrol_usd_l,
    ROUND(s.diisel_usd_gal    / 3.78541, 4)                     AS diesel_usd_l,
    ROUND((s.bensiin95_usd_gal / 3.78541) / v.eur_usd, 4)       AS petrol_eur_l,
    ROUND((s.diisel_usd_gal    / 3.78541) / v.eur_usd, 4)       AS diesel_eur_l,
    vrd.eia_varud_tuh_bbl                                        AS eia_varud_tuh_bbl,
    vrd.eia_varud_delta                                          AS eia_varud_delta,
    FALSE                                                        AS is_calculated,
    s.loaded_at                                                  AS add_timestamp
FROM staging.eia_spothinnad_raw s
LEFT JOIN staging.valuutakurss v
    ON date_trunc('week', v.week_date)::date = date_trunc('week', s.week_date)::date
LEFT JOIN varud vrd
    ON vrd.week_start_date = date_trunc('week', s.week_date)::date
{where_clause}
"""

INSERT_SQL = """
INSERT INTO public.ft_usa_prices
    (week_start_date, country_code, petrol_usd_l, diesel_usd_l,
     petrol_eur_l, diesel_eur_l, eia_varud_tuh_bbl, eia_varud_delta,
     is_calculated, add_timestamp)
{select}
ON CONFLICT (week_start_date, country_code) DO NOTHING
"""


def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.ft_usa_prices LIMIT 1)")
    return cur.fetchone()[0]


def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.ft_usa_prices")
    return cur.fetchone()[0]


def _needs_rebuild(cur) -> bool:
    cur.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'ft_usa_prices'
              AND column_name  = 'is_calculated'
        )
    """)
    return not cur.fetchone()[0]


def _fill_gaps(cur):
    """
    Leia lüngad dm_date_aggregation ja ft_usa_prices vahel.
    Täida lineaarse interpolatsiooniga ajalise kauguse järgi.
    eia_varud_delta ei interpoleerita — see on tuletatud arv ja lünga puhul NULL jäetakse.
    """
    cur.execute("""
        SELECT d.week_start_date
        FROM public.dm_date_aggregation d
        WHERE d.week_start_date BETWEEN (
            SELECT MIN(week_start_date) FROM public.ft_usa_prices WHERE country_code = 'US'
        ) AND (
            SELECT MAX(week_start_date) FROM public.ft_usa_prices WHERE country_code = 'US'
        )
        AND NOT EXISTS (
            SELECT 1 FROM public.ft_usa_prices f
            WHERE f.week_start_date = d.week_start_date
              AND f.country_code = 'US'
        )
        ORDER BY d.week_start_date
    """)

    missing_weeks = [row[0] for row in cur.fetchall()]

    if not missing_weeks:
        print("  ft_usa_prices: lünki ei leitud")
        return 0

    print(f"  ft_usa_prices: {len(missing_weeks)} puuduvat nädalat, interpoleerin...")

    total_filled = 0

    for missing_date in missing_weeks:
        cur.execute("""
            SELECT week_start_date, petrol_usd_l, diesel_usd_l,
                   petrol_eur_l, diesel_eur_l, eia_varud_tuh_bbl
            FROM public.ft_usa_prices
            WHERE country_code = 'US' AND week_start_date < %s AND is_calculated = FALSE
            ORDER BY week_start_date DESC
            LIMIT 1
        """, (missing_date,))
        prev = cur.fetchone()

        cur.execute("""
            SELECT week_start_date, petrol_usd_l, diesel_usd_l,
                   petrol_eur_l, diesel_eur_l, eia_varud_tuh_bbl
            FROM public.ft_usa_prices
            WHERE country_code = 'US' AND week_start_date > %s AND is_calculated = FALSE
            ORDER BY week_start_date ASC
            LIMIT 1
        """, (missing_date,))
        nxt = cur.fetchone()

        if prev is None or nxt is None:
            print(f"    {missing_date}: ei saa interpoleerida (puudub {'eelmine' if prev is None else 'järgmine'} punkt)")
            continue

        prev_date = prev[0]
        next_date = nxt[0]
        total_days = (next_date - prev_date).days
        ratio = (missing_date - prev_date).days / total_days if total_days > 0 else 0.5

        def interp(a, b):
            if a is None or b is None:
                return None
            return round(float(a) + ratio * (float(b) - float(a)), 4)

        cur.execute("""
            INSERT INTO public.ft_usa_prices
                (week_start_date, country_code, petrol_usd_l, diesel_usd_l,
                 petrol_eur_l, diesel_eur_l, eia_varud_tuh_bbl, eia_varud_delta,
                 is_calculated, add_timestamp)
            VALUES (%s, 'US', %s, %s, %s, %s, %s, NULL, TRUE, NOW())
            ON CONFLICT (week_start_date, country_code) DO NOTHING
        """, (
            missing_date,
            interp(prev[1], nxt[1]),  # petrol_usd_l
            interp(prev[2], nxt[2]),  # diesel_usd_l
            interp(prev[3], nxt[3]),  # petrol_eur_l
            interp(prev[4], nxt[4]),  # diesel_eur_l
            interp(prev[5], nxt[5]),  # eia_varud_tuh_bbl
        ))
        total_filled += cur.rowcount

    print(f"  ft_usa_prices: interpoleeritud {total_filled} rida")
    return total_filled


def run(hook):
    from contextlib import closing

    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:

                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'ft_usa_prices'
                    )
                """)
                table_exists = cur.fetchone()[0]

                if table_exists and _needs_rebuild(cur):
                    print("ft_usa_prices: vana skeem tuvastatud (puudub is_calculated) → täielik rebuild")
                    cur.execute("DROP TABLE public.ft_usa_prices")
                    table_exists = False
                elif table_exists:
                    cur.execute(ALTER_TABLE_SQL)

                cur.execute(CREATE_TABLE_SQL)

                if not table_exists or _table_is_empty(cur):
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
                print(f"ft_usa_prices: {inserted} päris rida lisatud")

                _fill_gaps(cur)

    return inserted