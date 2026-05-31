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

### Kriitilised Testid
Need blokeerivad pipeline'i, kui ebaõnnestuvad:
- `test_staging_bulletin_has_data` - Veendu, et staging tabelis on andmeid
- `test_dm_country_has_data` - Veendu, et dm_country tabelis on andmeid


### Hoiatuse Testid
Need logitakse, kuid ei blokeeri pipeline'i:
- `test_dm_country_completeness` - Kõik riigid staging tabelist peavad olemas olema dm_country tabelis
- `test_country_codes_valid_format` - Riikidel dm_country tabelis peavad olema kahekohalised koodid
- `test_bulletin_prices_positive` - Kõik hinnad peavad olema positiivsed
- `test_brent_prices_positive` - Kõik Brenti hinnad peavad olema positiivsed
- `test_exchange_rate_reasonable` - Vahetuskursid peavad olema realistlikus vahemikus
- `test_no_future_dates` - Ei tohi olla tuleviku kuupäevi
- `test_recent_data_exists` - Andmed ei tohiks olla vanemad kui 10 päeva


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