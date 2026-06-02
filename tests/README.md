# Data Quality Tests
Andmekvaliteedi testid kontrollimaks, et transformatsioonid töötavad korrektselt.

## Testide Käivitamine

### Airflow DAG-is (automaatne)

Testid käivituvad automaatselt pärast iga transformatsiooni käivitamist:
```
run_transforms() >> run_data_quality_tests()
```

Kui mõni test ebaõnnestub, DAG run märgitakse ebaõnnestunuks.

## Testide Kategooriad

### Staging testid (`STAGING_TESTS`)
Käivituvad kohe pärast laadimist (`run_staging_tests()` task):
- `test_staging_bulletin_has_data` — staging.bulletin_raw sisaldab andmeid
- `test_staging_brent_has_data` — staging.brent_raw sisaldab andmeid
- `test_staging_eia_spothinnad_has_data` — staging.eia_spothinnad_raw sisaldab andmeid
- `test_staging_eia_varud_has_data` — staging.eia_varud_raw sisaldab andmeid
- `test_staging_gpr_has_data` — staging.gpr_raw sisaldab andmeid
- `test_staging_yahoo_indikaatorid_has_data` — staging.yahoo_indikaatorid_raw sisaldab andmeid
- `test_bulletin_prices_positive` — bulletin_raw hinnad on positiivsed
- `test_brent_prices_positive` — brent_raw hinnad on positiivsed
- `test_exchange_rate_reasonable` — EUR/USD vahemikus 0.5–2.0
- `test_no_future_dates` — bulletin_raw ei sisalda tuleviku kuupäevi
- `test_staging_gaps` — tuvastab puuduvad nädalad kõigis staging tabelites (informatiivselt, ei blokeeri)

### Mart-kihi testid (`ALL_TESTS`)
Käivituvad pärast transformatsioone (`run_data_quality_tests()` task):
- `test_staging_bulletin_has_data` — andmete olemasolu
- `test_dm_country_has_data` — dm_country tabel pole tühi
- `test_dm_country_completeness` — kõik staging riigikoodid eksisteerivad dm_country tabelis
- `test_dm_country_no_nulls` — dm_country kriitilised veerud pole null
- `test_country_codes_valid_format` — riigikoodid on täpselt 2 tähemärki
- `test_bulletin_prices_positive` — hinnad on positiivsed
- `test_brent_prices_positive` — Brenti hinnad on positiivsed
- `test_exchange_rate_reasonable` — vahetuskurss realistlikus vahemikus
- `test_no_future_dates` — pole tuleviku kuupäevi
- `test_recent_data_exists` — viimased andmed pole vanemad kui 10 päeva
- `test_ft_price_forecast_has_data` — ft_price_forecast sisaldab nii ajaloolisi kui ennustuse ridu (EE)
- `test_ft_price_forecast_no_null_forecast` — forecast_price pole null üheski reas


## Uue Testi Lisamine

1. Ava `tests/data_quality_tests.py`
2. Kirjuta uus test funktsioon:

```python
def test_my_new_check(hook: PostgresHook) -> TestResult:
    """Test description"""
    result = hook.get_first("SELECT COUNT(*) FROM ...")
   
    count = result[0] if result else 0
    passed = count == 0  # või muu tingimus
    message = "Viga kirjeldus" if not passed else ""
   
    return TestResult("test_my_new_check", passed, message)
```

3. Lisa test `ALL_TESTS` nimekirja:
```python
ALL_TESTS = [
    # ...existing tests...
    test_my_new_check,
]
```

## Testide Kohandamine

### Ainult kriitiliste testide käivitamine

Muuda DAG failis:
```python
from data_quality_tests import run_critical_tests_only


results, passed, failed = run_critical_tests_only()
```

### Testide tulemuste logimine (mitte ebaõnnestuma)

Eemalda DAG-ist `raise Exception`:
```python
@task()
def run_data_quality_tests():
    results, passed, failed = run_all_tests()
    # Ära raise exception, lihtsalt logi
    print(f"Testide tulemused: {passed} õnnestus, {failed} ebaõnnestus")
    return {"passed": passed, "failed": failed}
```

## Testide Näited

### Referentsiaalne Terviklikkus
```python
def test_foreign_key_integrity(hook: PostgresHook) -> TestResult:
    result = hook.get_first("""
        SELECT COUNT(*)
        FROM fact_table f
        LEFT JOIN dim_table d ON f.dim_id = d.id
        WHERE d.id IS NULL
    """)
    return TestResult("fk_integrity", result[0] == 0)
```

### Duplikaatide Kontroll
```python
def test_no_duplicates(hook: PostgresHook) -> TestResult:
    result = hook.get_first("""
        SELECT COUNT(*) - COUNT(DISTINCT id)
        FROM my_table
    """)
    return TestResult("no_duplicates", result[0] == 0)
```

### Väärtuste Vahemik
```python
def test_values_in_range(hook: PostgresHook) -> TestResult:
    result = hook.get_first("""
        SELECT COUNT(*)
        FROM my_table
        WHERE value < 0 OR value > 100
    """)
    return TestResult("values_in_range", result[0] == 0)
```