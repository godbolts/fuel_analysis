"""
public.ft_exchange_rate
------------------------
Allikas: staging.valuutakurss
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult read, kus week_start_date > MAX(week_start_date)
  4. Lüngad nädalates   → täida lineaarse interpolatsiooniga
  5. is_calculated      → FALSE päris andmetel, TRUE interpoleeritud ridadel

Migratsioon:
  Kui tabelis puudub is_calculated veerg (vana skeem), tehakse täielik rebuild.
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_exchange_rate (
    week_start_date DATE        NOT NULL PRIMARY KEY,
    eur_usd         NUMERIC(8,6),
    usd_eur         NUMERIC(8,6),
    is_calculated   BOOLEAN     NOT NULL DEFAULT FALSE,
    add_timestamp   TIMESTAMPTZ
);
"""

SELECT_SQL = """
SELECT
    date_trunc('week', week_date)::date     AS week_start_date,
    eur_usd                                 AS eur_usd,
    ROUND(1.0 / eur_usd, 6)                AS usd_eur,
    FALSE                                   AS is_calculated,
    loaded_at                               AS add_timestamp
FROM staging.valuutakurss
WHERE eur_usd IS NOT NULL
{where_clause}
"""

INSERT_SQL = """
INSERT INTO public.ft_exchange_rate
    (week_start_date, eur_usd, usd_eur, is_calculated, add_timestamp)
{select}
ON CONFLICT (week_start_date) DO NOTHING
"""


def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.ft_exchange_rate LIMIT 1)")
    return cur.fetchone()[0]


def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.ft_exchange_rate")
    return cur.fetchone()[0]


def _needs_rebuild(cur) -> bool:
    cur.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'ft_exchange_rate'
              AND column_name  = 'is_calculated'
        )
    """)
    return not cur.fetchone()[0]


def _fill_gaps(cur):
    """
    Leia lüngad dm_date_aggregation ja ft_exchange_rate vahel.
    Täida lineaarse interpolatsiooniga ajalise kauguse järgi.
    usd_eur arvutatakse interpoleeritud eur_usd pealt (mitte eraldi interpoleeritakse).
    """
    cur.execute("""
        SELECT d.week_start_date
        FROM public.dm_date_aggregation d
        WHERE d.week_start_date BETWEEN (
            SELECT MIN(week_start_date) FROM public.ft_exchange_rate
        ) AND (
            SELECT MAX(week_start_date) FROM public.ft_exchange_rate
        )
        AND NOT EXISTS (
            SELECT 1 FROM public.ft_exchange_rate f
            WHERE f.week_start_date = d.week_start_date
        )
        ORDER BY d.week_start_date
    """)

    missing_weeks = [row[0] for row in cur.fetchall()]

    if not missing_weeks:
        print("  ft_exchange_rate: lünki ei leitud")
        return 0

    print(f"  ft_exchange_rate: {len(missing_weeks)} puuduvat nädalat, interpoleerin...")

    total_filled = 0

    for missing_date in missing_weeks:
        cur.execute("""
            SELECT week_start_date, eur_usd
            FROM public.ft_exchange_rate
            WHERE week_start_date < %s AND is_calculated = FALSE
            ORDER BY week_start_date DESC
            LIMIT 1
        """, (missing_date,))
        prev = cur.fetchone()

        cur.execute("""
            SELECT week_start_date, eur_usd
            FROM public.ft_exchange_rate
            WHERE week_start_date > %s AND is_calculated = FALSE
            ORDER BY week_start_date ASC
            LIMIT 1
        """, (missing_date,))
        nxt = cur.fetchone()

        if prev is None or nxt is None:
            print(f"    {missing_date}: ei saa interpoleerida (puudub {'eelmine' if prev is None else 'järgmine'} punkt)")
            continue

        prev_date, prev_eur_usd = prev
        next_date, next_eur_usd = nxt
        total_days = (next_date - prev_date).days
        ratio = (missing_date - prev_date).days / total_days if total_days > 0 else 0.5

        eur_usd_interp = round(float(prev_eur_usd) + ratio * (float(next_eur_usd) - float(prev_eur_usd)), 6)
        usd_eur_interp = round(1.0 / eur_usd_interp, 6) if eur_usd_interp else None

        cur.execute("""
            INSERT INTO public.ft_exchange_rate
                (week_start_date, eur_usd, usd_eur, is_calculated, add_timestamp)
            VALUES (%s, %s, %s, TRUE, NOW())
            ON CONFLICT (week_start_date) DO NOTHING
        """, (missing_date, eur_usd_interp, usd_eur_interp))
        total_filled += cur.rowcount

    print(f"  ft_exchange_rate: interpoleeritud {total_filled} rida")
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
                          AND table_name = 'ft_exchange_rate'
                    )
                """)
                table_exists = cur.fetchone()[0]

                if table_exists and _needs_rebuild(cur):
                    print("ft_exchange_rate: vana skeem tuvastatud (puudub is_calculated) → täielik rebuild")
                    cur.execute("DROP TABLE public.ft_exchange_rate")
                    table_exists = False

                cur.execute(CREATE_TABLE_SQL)

                if not table_exists or _table_is_empty(cur):
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
                print(f"ft_exchange_rate: {inserted} päris rida lisatud")

                _fill_gaps(cur)

    return inserted