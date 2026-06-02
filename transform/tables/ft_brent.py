"""
public.ft_brent
----------------
Allikas: staging.brent_raw + staging.valuutakurss
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult read, kus week_start_date > MAX(week_start_date)
  4. Lüngad nädalates   → täida lineaarse interpolatsiooniga
  5. is_calculated      → FALSE päris andmetel, TRUE interpoleeritud ridadel

Migratsioon:
  Kui tabelis puudub is_calculated veerg (vana skeem), tehakse täielik rebuild.

Teisendused:
  USD/barrel → EUR/barrel (jagatud EUR/USD kursiga)
  USD/barrel → USD/liiter (jagatud 158.987-ga)
  USD/barrel → EUR/liiter (jagatud EUR/USD kursiga ja 158.987-ga)
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_brent (
    week_start_date DATE         NOT NULL PRIMARY KEY,
    usd_bbl         NUMERIC(8,2),
    eur_bbl         NUMERIC(8,2),
    usd_l           NUMERIC(8,4),
    eur_l           NUMERIC(8,4),
    eur_usd_rate    NUMERIC(8,6),
    is_calculated   BOOLEAN      NOT NULL DEFAULT FALSE,
    add_timestamp   TIMESTAMPTZ
);
"""

SELECT_SQL = """
SELECT
    date_trunc('week', b.week_date)::date            AS week_start_date,
    b.brent_usd_bbl                                  AS usd_bbl,
    ROUND(b.brent_usd_bbl / v.eur_usd, 2)            AS eur_bbl,
    ROUND(b.brent_usd_bbl / 158.987, 4)              AS usd_l,
    ROUND(b.brent_usd_bbl / 158.987 / v.eur_usd, 4)  AS eur_l,
    v.eur_usd                                         AS eur_usd_rate,
    FALSE                                             AS is_calculated,
    b.loaded_at                                       AS add_timestamp
FROM staging.brent_raw b
LEFT JOIN staging.valuutakurss v
    ON date_trunc('week', v.week_date)::date = date_trunc('week', b.week_date)::date
{where_clause}
"""

INSERT_SQL = """
INSERT INTO public.ft_brent
    (week_start_date, usd_bbl, eur_bbl, usd_l, eur_l, eur_usd_rate, is_calculated, add_timestamp)
{select}
ON CONFLICT (week_start_date) DO NOTHING
"""


def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.ft_brent LIMIT 1)")
    return cur.fetchone()[0]


def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.ft_brent")
    return cur.fetchone()[0]


def _needs_rebuild(cur) -> bool:
    cur.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'ft_brent'
              AND column_name  = 'is_calculated'
        )
    """)
    return not cur.fetchone()[0]


def _fill_gaps(cur):
    """
    Leia lüngad dm_date_aggregation ja ft_brent vahel.
    Täida lineaarse interpolatsiooniga ajalise kauguse järgi.
    """
    cur.execute("""
        SELECT d.week_start_date
        FROM public.dm_date_aggregation d
        WHERE d.week_start_date BETWEEN (
            SELECT MIN(week_start_date) FROM public.ft_brent
        ) AND (
            SELECT MAX(week_start_date) FROM public.ft_brent
        )
        AND NOT EXISTS (
            SELECT 1 FROM public.ft_brent f
            WHERE f.week_start_date = d.week_start_date
        )
        ORDER BY d.week_start_date
    """)

    missing_weeks = [row[0] for row in cur.fetchall()]

    if not missing_weeks:
        print("  ft_brent: lünki ei leitud")
        return 0

    print(f"  ft_brent: {len(missing_weeks)} puuduvat nädalat, interpoleerin...")

    total_filled = 0

    for missing_date in missing_weeks:
        cur.execute("""
            SELECT week_start_date, usd_bbl, eur_bbl, usd_l, eur_l, eur_usd_rate
            FROM public.ft_brent
            WHERE week_start_date < %s AND is_calculated = FALSE
            ORDER BY week_start_date DESC
            LIMIT 1
        """, (missing_date,))
        prev = cur.fetchone()

        cur.execute("""
            SELECT week_start_date, usd_bbl, eur_bbl, usd_l, eur_l, eur_usd_rate
            FROM public.ft_brent
            WHERE week_start_date > %s AND is_calculated = FALSE
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
            INSERT INTO public.ft_brent
                (week_start_date, usd_bbl, eur_bbl, usd_l, eur_l, eur_usd_rate, is_calculated, add_timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, NOW())
            ON CONFLICT (week_start_date) DO NOTHING
        """, (
            missing_date,
            interp(prev[1], nxt[1]),  # usd_bbl
            interp(prev[2], nxt[2]),  # eur_bbl
            interp(prev[3], nxt[3]),  # usd_l
            interp(prev[4], nxt[4]),  # eur_l
            interp(prev[5], nxt[5]),  # eur_usd_rate
        ))
        total_filled += cur.rowcount

    print(f"  ft_brent: interpoleeritud {total_filled} rida")
    return total_filled


def run(hook):
    from contextlib import closing

    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:

                # Migratsioon: vana skeem ilma is_calculated → täielik rebuild
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'ft_brent'
                    )
                """)
                table_exists = cur.fetchone()[0]

                if table_exists and _needs_rebuild(cur):
                    print("ft_brent: vana skeem tuvastatud (puudub is_calculated) → täielik rebuild")
                    cur.execute("DROP TABLE public.ft_brent")
                    table_exists = False

                cur.execute(CREATE_TABLE_SQL)

                if not table_exists or _table_is_empty(cur):
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
                print(f"ft_brent: {inserted} päris rida lisatud")

                _fill_gaps(cur)

    return inserted