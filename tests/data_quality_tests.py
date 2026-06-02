"""
Data Kvaliteedi testid.
------------------
Testib andmete terviklikkust ja kvaliteeti pärast transformatsioone.
"""

try:
    from airflow.providers.postgres.hooks.postgres import PostgresHook
except ImportError:
    from airflow.hooks.postgres_hook import PostgresHook

from typing import List, Tuple

class TestResult:
    """Container for test results"""
    def __init__(self, test_name: str, passed: bool, message: str = ""):
        self.test_name = test_name
        self.passed = passed
        self.message = message
   
    def __str__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        msg = f" - {self.message}" if self.message else ""
        return f"{status}: {self.test_name}{msg}"

def test_dm_country_completeness(hook: PostgresHook) -> TestResult:
    """Kontroll, et kõik soovitud riigid staging.bulletin_raw tabelis on olemas dm_country tabelis"""
    result = hook.get_first("""
        SELECT COUNT(*)
        FROM staging.bulletin_raw sb
        LEFT JOIN public.dm_country dc ON sb.country = dc.country_code_2
        WHERE sb.country IS NOT NULL
          AND dc.country_code_2 IS NULL
    """)
   
    missing_count = result[0] if result else 0
    passed = missing_count == 0
    message = f"{missing_count} riiki puudub dm_country tabelist" if not passed else ""
   
    return TestResult("dm_country_completeness", passed, message)

def test_dm_country_no_nulls(hook: PostgresHook) -> TestResult:
    """Kontroll, et dm_country tabelis ei ole null väärtuseid võtmeveerutites"""
    result = hook.get_first("""
        SELECT COUNT(*)
        FROM public.dm_country
        WHERE country_code_2 IS NULL
           OR country_name IS NULL
    """)
   
    null_count = result[0] if result else 0
    passed = null_count == 0
    message = f"{null_count} rida sisaldab null väärtusi" if not passed else ""
   
    return TestResult("dm_country_no_nulls", passed, message)

def test_bulletin_prices_positive(hook: PostgresHook) -> TestResult:
    """Kontroll, et staging.bulletin_raw tabelis olevad kütushinnad on positiivsed"""
    result = hook.get_first("""
        SELECT COUNT(*)
        FROM staging.bulletin_raw
        WHERE (euro95_eur_kl IS NOT NULL AND euro95_eur_kl <= 0)
           OR (diesel_eur_kl IS NOT NULL AND diesel_eur_kl <= 0)
    """)
   
    invalid_count = result[0] if result else 0
    passed = invalid_count == 0
    message = f"{invalid_count} rida sisaldab negatiivseid/null hindu" if not passed else ""
   
    return TestResult("bulletin_prices_positive", passed, message)

def test_brent_prices_positive(hook: PostgresHook) -> TestResult:
    """Kontroll, et staging.brent_raw tabelis olevad Brent toornafta hinnad on positiivsed"""
    result = hook.get_first("""
        SELECT COUNT(*)
        FROM staging.brent_raw
        WHERE brent_usd_bbl IS NOT NULL AND brent_usd_bbl <= 0
    """)
   
    invalid_count = result[0] if result else 0
    passed = invalid_count == 0
    message = f"{invalid_count} rida sisaldab negatiivseid Brent hindu" if not passed else ""
   
    return TestResult("brent_prices_positive", passed, message)

def test_exchange_rate_reasonable(hook: PostgresHook) -> TestResult:
    """Kontroll, et EUR/USD vahetuskursid on mõõdukad (0.5 - 2.0)"""
    result = hook.get_first("""
        SELECT COUNT(*)
        FROM staging.valuutakurss
        WHERE week_date IS NOT NULL
          AND (eur_usd < 0.5 OR eur_usd > 2.0)
    """)
   
    invalid_count = result[0] if result else 0
    passed = invalid_count == 0
    message = f"{invalid_count} rida sisaldab ebarealistlikke vahetuskursse" if not passed else ""
   
    return TestResult("exchange_rate_reasonable", passed, message)

def test_no_future_dates(hook: PostgresHook) -> TestResult:
    """Kontroll, et tabelis ei ole tuleviku kuupäevi"""
    result = hook.get_first("""
        SELECT COUNT(*)
        FROM staging.bulletin_raw
        WHERE week_date > CURRENT_DATE
    """)
   
    future_count = result[0] if result else 0
    passed = future_count == 0
    message = f"{future_count} rida sisaldab tuleviku kuupäevi" if not passed else ""
   
    return TestResult("no_future_dates", passed, message)

def test_staging_bulletin_has_data(hook: PostgresHook) -> TestResult:
    """Kontroll, et staging.bulletin_raw tabelis on andmeid"""
    result = hook.get_first("SELECT COUNT(*) FROM staging.bulletin_raw")
   
    row_count = result[0] if result else 0
    passed = row_count > 0
    message = f"Tabel on tühi" if not passed else f"{row_count} rida"
   
    return TestResult("staging_bulletin_has_data", passed, message)

def test_dm_country_has_data(hook: PostgresHook) -> TestResult:
    """Kontroll, et dm_country tabelis on andmeid"""
    result = hook.get_first("SELECT COUNT(*) FROM public.dm_country")
   
    row_count = result[0] if result else 0
    passed = row_count > 0
    message = f"Tabel on tühi" if not passed else f"{row_count} rida"
   
    return TestResult("dm_country_has_data", passed, message)

def test_recent_data_exists(hook: PostgresHook) -> TestResult:
    """Kontroll, et meil on värsked andmed"""
    result = hook.get_first("""
        SELECT MAX(week_date)
        FROM staging.bulletin_raw
    """)
   
    if not result or not result[0]:
        return TestResult("recent_data_exists", False, "Pole ühtegi kuupäeva")
   
    max_date = result[0]
   
    # Check if max_date is a string and needs parsing
    if isinstance(max_date, str):
        from datetime import datetime
        max_date = datetime.strptime(max_date.split()[0], '%Y-%m-%d').date()
   
    result_days = hook.get_first("""
        SELECT CURRENT_DATE - %s::DATE
    """, parameters=(max_date,))
   
    days_old = result_days[0] if result_days else 999
    passed = days_old <= 10
    message = f"Viimased andmed on {days_old} päeva vanad" if not passed else f"Viimased andmed on {days_old} päeva vanad"
   
    return TestResult("recent_data_exists", passed, message)

def test_country_codes_valid_format(hook: PostgresHook) -> TestResult:
    """Kontroll, et dm_country tabelis olevad riigikoodid oleksid kaksetähelised"""
    result = hook.get_first("""
        SELECT COUNT(*)
        FROM public.dm_country
        WHERE LENGTH(country_code_2) != 2
    """)
   
    invalid_count = result[0] if result else 0
    passed = invalid_count == 0
    message = f"{invalid_count} riiki sisaldab vigast koodi" if not passed else ""
   
    return TestResult("country_codes_valid_format", passed, message)

def test_staging_brent_has_data(hook: PostgresHook) -> TestResult:
    """Kontroll, et staging.brent_raw tabelis on andmeid"""
    result = hook.get_first("SELECT COUNT(*) FROM staging.brent_raw")
    row_count = result[0] if result else 0
    passed = row_count > 0
    message = "Tabel on tühi" if not passed else f"{row_count} rida"
    return TestResult("staging_brent_has_data", passed, message)

def test_staging_eia_spothinnad_has_data(hook: PostgresHook) -> TestResult:
    """Kontroll, et staging.eia_spothinnad_raw tabelis on andmeid"""
    result = hook.get_first("SELECT COUNT(*) FROM staging.eia_spothinnad_raw")
    row_count = result[0] if result else 0
    passed = row_count > 0
    message = "Tabel on tühi" if not passed else f"{row_count} rida"
    return TestResult("staging_eia_spothinnad_has_data", passed, message)

def test_staging_eia_varud_has_data(hook: PostgresHook) -> TestResult:
    """Kontroll, et staging.eia_varud_raw tabelis on andmeid"""
    result = hook.get_first("SELECT COUNT(*) FROM staging.eia_varud_raw")
    row_count = result[0] if result else 0
    passed = row_count > 0
    message = "Tabel on tühi" if not passed else f"{row_count} rida"
    return TestResult("staging_eia_varud_has_data", passed, message)

def test_staging_gpr_has_data(hook: PostgresHook) -> TestResult:
    """Kontroll, et staging.gpr_raw tabelis on andmeid"""
    result = hook.get_first("SELECT COUNT(*) FROM staging.gpr_raw")
    row_count = result[0] if result else 0
    passed = row_count > 0
    message = "Tabel on tühi" if not passed else f"{row_count} rida"
    return TestResult("staging_gpr_has_data", passed, message)

def test_staging_yahoo_indikaatorid_has_data(hook: PostgresHook) -> TestResult:
    """Kontroll, et staging.yahoo_indikaatorid_raw tabelis on andmeid"""
    result = hook.get_first("SELECT COUNT(*) FROM staging.yahoo_indikaatorid_raw")
    row_count = result[0] if result else 0
    passed = row_count > 0
    message = "Tabel on tühi" if not passed else f"{row_count} rida"
    return TestResult("staging_yahoo_indikaatorid_has_data", passed, message)

def test_ft_price_forecast_has_data(hook: PostgresHook) -> TestResult:
    """Kontroll, et public.ft_price_forecast tabelis on ajaloolisi ja ennustuse ridu"""
    result = hook.get_first("""
        SELECT
            COUNT(*) FILTER (WHERE is_forecast = FALSE) AS historical,
            COUNT(*) FILTER (WHERE is_forecast = TRUE)  AS forecast
        FROM public.ft_price_forecast
        WHERE country_code = 'EE'
    """)
    historical = result[0] if result else 0
    forecast   = result[1] if result else 0
    passed = historical > 0 and forecast > 0
    if not passed:
        message = f"historical={historical}, forecast={forecast} — oodatakse mõlemaid"
    else:
        message = f"{historical} ajaloolist + {forecast} ennustuse rida (EE)"
    return TestResult("ft_price_forecast_has_data", passed, message)

def test_ft_price_forecast_no_null_forecast(hook: PostgresHook) -> TestResult:
    """Kontroll, et forecast_price ei ole null üheski reas"""
    result = hook.get_first("""
        SELECT COUNT(*)
        FROM public.ft_price_forecast
        WHERE forecast_price IS NULL
    """)
    null_count = result[0] if result else 0
    passed = null_count == 0
    message = f"{null_count} real puudub forecast_price" if not passed else ""
    return TestResult("ft_price_forecast_no_null_forecast", passed, message)


def test_staging_gaps(hook: PostgresHook) -> TestResult:
    """Informatiivne kontroll: genereerib täieliku oodatava nädala seeria min→max
    ja leiab millised kuupäevad tabelis PUUDUVAD.
    Test läbib alati — eesmärk on logida puuduvad nädalad, mitte blokeerida pipeline.
    NB: valuutakurss kasutab gap-põhist kontrolli (>9 päeva), kuna DST tõttu
    ei ole Yahoo Finance andmed täpselt 7-päevase intervalliga."""
    # Tabelid kus kasutatakse generate_series (täpselt 7-päevane kadents)
    weekly_checks = [
        ("bulletin_raw",       "week_date",  "staging.bulletin_raw",          "country='EE'"),
        ("brent_raw",          "week_date",  "staging.brent_raw",             None),
        ("eia_spothinnad_raw", "week_date",  "staging.eia_spothinnad_raw",    None),
        ("eia_varud_raw",      "varud_date", "staging.eia_varud_raw",         None),
        ("yahoo_indikaatorid", "week_date",  "staging.yahoo_indikaatorid_raw",None),
    ]

    gap_report = []

    for tabel, date_col, source, where in weekly_checks:
        w = f"WHERE {where}" if where else ""
        rows = hook.get_records(f"""
            SELECT gs::date AS puuduv_nadal
            FROM generate_series(
                (SELECT MIN({date_col}) FROM {source} {w}),
                (SELECT MAX({date_col}) FROM {source} {w}),
                '7 days'::interval
            ) gs
            WHERE gs::date NOT IN (
                SELECT {date_col} FROM {source} {w}
            )
            ORDER BY gs
        """)
        if rows:
            dates = ", ".join(str(r[0]) for r in rows)
            gap_report.append(f"{tabel}: {len(rows)} puuduvat nädalat: {dates}")

    # valuutakurss: gap-põhine kontroll (DST põhjustab ~8-päevaseid intervalle)
    rows = hook.get_records("""
        SELECT week_date, next_date, vahe
        FROM (
            SELECT week_date,
                   LEAD(week_date) OVER (ORDER BY week_date) AS next_date,
                   LEAD(week_date) OVER (ORDER BY week_date) - week_date AS vahe
            FROM staging.valuutakurss
        ) t
        WHERE vahe > 9
        ORDER BY week_date
    """)
    if rows:
        gaps = ", ".join(f"{r[0]}→{r[1]} ({r[2]}p)" for r in rows)
        gap_report.append(f"valuutakurss: {len(rows)} suurt vahet (>9p): {gaps}")

    if gap_report:
        msg = "Puuduvad nädalad:\n    " + "\n    ".join(gap_report)
        print(f"\n  ⚠ staging_gaps: {msg}")
    else:
        msg = "kõik nädalad on olemas"

    return TestResult("staging_gaps", True, msg)


STAGING_TESTS = [
    test_staging_bulletin_has_data,
    test_staging_brent_has_data,
    test_staging_eia_spothinnad_has_data,
    test_staging_eia_varud_has_data,
    test_staging_gpr_has_data,
    test_staging_yahoo_indikaatorid_has_data,
    test_bulletin_prices_positive,
    test_brent_prices_positive,
    test_exchange_rate_reasonable,
    test_no_future_dates,
    test_staging_gaps,
]

# Test suite configuration
ALL_TESTS = [
    test_staging_bulletin_has_data,
    test_dm_country_has_data,
    test_dm_country_completeness,
    test_dm_country_no_nulls,
    test_country_codes_valid_format,
    test_bulletin_prices_positive,
    test_brent_prices_positive,
    test_exchange_rate_reasonable,
    test_no_future_dates,
    test_recent_data_exists,
    test_ft_price_forecast_has_data,
    test_ft_price_forecast_no_null_forecast,
]

def run_all_tests(postgres_conn_id: str = "analytics_db") -> Tuple[List[TestResult], int, int]:
    """
    Run all data quality tests
   
    Returns:
        Tuple of (test_results, passed_count, failed_count)
    """
    hook = PostgresHook(postgres_conn_id=postgres_conn_id)
    results = []
   
    print("\n" + "="*60)
    print("ANDMEKVALITEEDI TESTID")
    print("="*60 + "\n")
   
    for test_func in ALL_TESTS:
        try:
            result = test_func(hook)
            results.append(result)
            print(f"  {result}")
        except Exception as e:
            error_result = TestResult(test_func.__name__, False, f"Viga: {str(e)}")
            results.append(error_result)
            print(f"  {error_result}")
   
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
   
    print("\n" + "-"*60)
    print(f"Kokku: {len(results)} testi | ✓ {passed} õnnestus | ✗ {failed} ebaõnnestus")
    print("="*60 + "\n")
   
    return results, passed, failed

def run_staging_tests(postgres_conn_id: str = "analytics_db") -> Tuple[List[TestResult], int, int]:
    """
    Jooksutab staging-kihi kvaliteeditestid — käivitatakse kohe pärast laadimist.
    """
    hook = PostgresHook(postgres_conn_id=postgres_conn_id)
    results = []

    print("\n" + "="*60)
    print("STAGING KVALITEEDITESTID")
    print("="*60 + "\n")

    for test_func in STAGING_TESTS:
        try:
            result = test_func(hook)
            results.append(result)
            print(f"  {result}")
        except Exception as e:
            error_result = TestResult(test_func.__name__, False, f"Viga: {str(e)}")
            results.append(error_result)
            print(f"  {error_result}")

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    print("\n" + "-"*60)
    print(f"Kokku: {len(results)} testi | ✓ {passed} õnnestus | ✗ {failed} ebaõnnestus")
    print("="*60 + "\n")

    return results, passed, failed


def run_critical_tests_only(postgres_conn_id: str = "analytics_db") -> Tuple[List[TestResult], int, int]:
    """
    Run only critical tests that should block the pipeline
    """
    critical_tests = [
        test_staging_bulletin_has_data,
        test_dm_country_has_data
    ]
   
    hook = PostgresHook(postgres_conn_id=postgres_conn_id)
    results = []
   
    print("\n" + "="*60)
    print("KRIITILISED TESTID")
    print("="*60 + "\n")
   
    for test_func in critical_tests:
        try:
            result = test_func(hook)
            results.append(result)
            print(f"  {result}")
        except Exception as e:
            error_result = TestResult(test_func.__name__, False, f"Viga: {str(e)}")
            results.append(error_result)
            print(f"  {error_result}")
   
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
   
    print("\n" + "-"*60)
    print(f"Kokku: {len(results)} testi | ✓ {passed} õnnestus | ✗ {failed} ebaõnnestus")
    print("="*60 + "\n")
   
    return results, passed, failed

if __name__ == "__main__":
    # For local testing
    results, passed, failed = run_all_tests()
    if failed > 0:
        exit(1)
