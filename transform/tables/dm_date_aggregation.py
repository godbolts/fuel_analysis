"""
public.dm_date_aggregation
---------------
Kalendri dimensioonitabel — üks rida iga nädala kohta.
Allikas: genereeritud andmestiku vahemiku pealt (staging.bulletin_raw MIN/MAX)
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → lisa ainult uued nädalad > MAX(week_start_date)
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.dm_date_aggregation (
    week_start_date   DATE         NOT NULL PRIMARY KEY,
    week_end_date     DATE         NOT NULL,
    year              SMALLINT     NOT NULL,
    quarter           SMALLINT     NOT NULL,
    month             SMALLINT     NOT NULL,
    month_name        VARCHAR(10)  NOT NULL,
    week_number       SMALLINT     NOT NULL,
    is_current_week   BOOLEAN      NOT NULL,
    add_timestamp     TIMESTAMPTZ  DEFAULT NOW()
);
"""

INSERT_SQL = """
INSERT INTO public.dm_date_aggregation
    (week_start_date, week_end_date, year, quarter, month,
     month_name, week_number, is_current_week, add_timestamp)
SELECT
    week_start                                          AS week_start_date,
    week_start + INTERVAL '6 days'                      AS week_end_date,
    EXTRACT(YEAR    FROM week_start)::SMALLINT          AS year,
    EXTRACT(QUARTER FROM week_start)::SMALLINT          AS quarter,
    EXTRACT(MONTH   FROM week_start)::SMALLINT          AS month,
    TO_CHAR(week_start, 'Month')                        AS month_name,
    EXTRACT(WEEK    FROM week_start)::SMALLINT          AS week_number,
    date_trunc('week', CURRENT_DATE)::date = week_start AS is_current_week,
    NOW()                                               AS add_timestamp
FROM generate_series(
    date_trunc('week', (SELECT MIN(week_date) FROM staging.bulletin_raw))::date,
    date_trunc('week', CURRENT_DATE)::date,
    INTERVAL '1 week'
) AS gs(week_start)
{where_clause}
ON CONFLICT (week_start_date) DO UPDATE SET
    is_current_week = EXCLUDED.is_current_week,
    add_timestamp   = EXCLUDED.add_timestamp;
"""


def _table_is_empty(cur) -> bool:
    cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.dm_date_aggregation LIMIT 1)")
    return cur.fetchone()[0]


def _max_week(cur):
    cur.execute("SELECT MAX(week_start_date) FROM public.dm_date_aggregation")
    return cur.fetchone()[0]


def run(hook):
    from contextlib import closing

    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:

                cur.execute(CREATE_TABLE_SQL)

                if _table_is_empty(cur):
                    where_clause = ""
                    print("dm_date_aggregation: täida kõik read")
                else:
                    max_week = _max_week(cur)
                    where_clause = f"WHERE week_start > '{max_week}'"
                    print(f"dm_date_aggregation: inkrementaalne laadimine alates {max_week}")

                insert_sql = INSERT_SQL.format(where_clause=where_clause)
                cur.execute(insert_sql)
                inserted = cur.rowcount
                print(f"dm_date_aggregation: {inserted} rida lisatud/uuendatud")

    return inserted