"""
public.ft_market
-----------------
Allikas: staging.yahoo_indikaatorid_raw (DXY, VIX, OVX)
         staging.gpr_raw (GPR päevane → nädala keskmine)
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult read, kus week_start_date > MAX(week_start_date)
  4. Lüngad nädalates   → täida lineaarse interpolatsiooniga
  5. is_calculated      → FALSE päris andmetel, TRUE interpoleeritud ridadel

Migratsioon:
  - Vana veeru nimed (dxy, vix, ovx) nimetatakse ümber (dollar_index, snp_index, oil_index)
  - Kui puudub is_calculated veerg, tehakse täielik rebuild
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_market (
    week_start_date DATE         NOT NULL PRIMARY KEY,
    dollar_index    NUMERIC(8,4),
    snp_index       NUMERIC(8,4),
    oil_index       NUMERIC(8,4),
    gpr_avg         NUMERIC(10,2),
    is_calculated   BOOLEAN      NOT NULL DEFAULT FALSE,
    add_timestamp   TIMESTAMPTZ
);
"""

SELECT_SQL = """
SELECT
    date_trunc('week', y.week_date)::date   AS week_start_date,
    y.dxy                                   AS dollar_index,
    y.vix                                   AS snp_index,
    y.ovx                                   AS oil_index,
    ROUND(AVG(g.gpr), 2)                    AS gpr_avg,
    FALSE                                   AS is_calculated,
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
    (week_start_date, dollar_index, snp_index, oil_index, gpr_avg, is_calculated, add_timestamp)
{select}
ON CONFLICT (week_start_date) DO NOTHING
"""


def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.ft_market LIMIT 1)")
    return cur.fetchone()[0]


def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.ft_market")
    return cur.fetchone()[0]


def _needs_rebuild(cur) -> bool:
    cur.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'ft_market'
              AND column_name  = 'is_calculated'
        )
    """)
    return not cur.fetchone()[0]


def _migrate_column_names(cur):
    """Nimeta vanad veerud ümber kui need on veel vana nimega."""
    renames = [
        ("dxy", "dollar_index"),
        ("vix", "snp_index"),
        ("ovx", "oil_index"),
    ]
    for old_name, new_name in renames:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name   = 'ft_market'
                  AND column_name  = %s
            )
        """, (old_name,))
        if cur.fetchone()[0]:
            cur.execute(f"ALTER TABLE public.ft_market RENAME COLUMN {old_name} TO {new_name}")
            print(f"  ft_market: veerg '{old_name}' → '{new_name}'")


def _fill_gaps(cur):
    """
    Leia lüngad dm_date_aggregation ja ft_market vahel.
    Täida lineaarse interpolatsiooniga ajalise kauguse järgi.
    gpr_avg interpoleeritakse samuti — see on nädala keskmine aga lünga puhul parim lähend.
    """
    cur.execute("""
        SELECT d.week_start_date
        FROM public.dm_date_aggregation d
        WHERE d.week_start_date BETWEEN (
            SELECT MIN(week_start_date) FROM public.ft_market
        ) AND (
            SELECT MAX(week_start_date) FROM public.ft_market
        )
        AND NOT EXISTS (
            SELECT 1 FROM public.ft_market f
            WHERE f.week_start_date = d.week_start_date
        )
        ORDER BY d.week_start_date
    """)

    missing_weeks = [row[0] for row in cur.fetchall()]

    if not missing_weeks:
        print("  ft_market: lünki ei leitud")
        return 0

    print(f"  ft_market: {len(missing_weeks)} puuduvat nädalat, interpoleerin...")

    total_filled = 0

    for missing_date in missing_weeks:
        cur.execute("""
            SELECT week_start_date, dollar_index, snp_index, oil_index, gpr_avg
            FROM public.ft_market
            WHERE week_start_date < %s AND is_calculated = FALSE
            ORDER BY week_start_date DESC
            LIMIT 1
        """, (missing_date,))
        prev = cur.fetchone()

        cur.execute("""
            SELECT week_start_date, dollar_index, snp_index, oil_index, gpr_avg
            FROM public.ft_market
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
            INSERT INTO public.ft_market
                (week_start_date, dollar_index, snp_index, oil_index, gpr_avg, is_calculated, add_timestamp)
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
            ON CONFLICT (week_start_date) DO NOTHING
        """, (
            missing_date,
            interp(prev[1], nxt[1]),  # dollar_index
            interp(prev[2], nxt[2]),  # snp_index
            interp(prev[3], nxt[3]),  # oil_index
            interp(prev[4], nxt[4]),  # gpr_avg
        ))
        total_filled += cur.rowcount

    print(f"  ft_market: interpoleeritud {total_filled} rida")
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
                          AND table_name = 'ft_market'
                    )
                """)
                table_exists = cur.fetchone()[0]

                if table_exists and _needs_rebuild(cur):
                    print("ft_market: vana skeem tuvastatud (puudub is_calculated) → täielik rebuild")
                    cur.execute("DROP TABLE public.ft_market")
                    table_exists = False
                elif table_exists:
                    # Nimeta veerud ümber kui vajalik
                    _migrate_column_names(cur)

                cur.execute(CREATE_TABLE_SQL)

                if not table_exists or _table_is_empty(cur):
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
                print(f"ft_market: {inserted} päris rida lisatud")

                _fill_gaps(cur)

    return inserted