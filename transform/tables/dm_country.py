"""
public.dm_country
-------------------
Allikas: staging.bulletin_raw (distinct country_code) + restcountries.com API
         staging.eia_spothinnad_raw (kui eksisteerib ja sisaldab andmeid, lisatakse 'US')
Loogika:
  1. Tabel puudub       → loo tabel + täida kõik read
  2. Tabel on tühi      → täida kõik read
  3. Tabelis on andmed  → upsert (rahvastikuarv võib ajas muutuda)
"""
 
import requests
 
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.dm_country (
    country_code_2  CHAR(2)      NOT NULL PRIMARY KEY,
    country_code_3  CHAR(3),
    country_name    VARCHAR(100),
    capital         VARCHAR(100),
    population      BIGINT,
    add_timestamp   TIMESTAMPTZ  DEFAULT NOW()
);
"""
 
UPSERT_SQL = """
INSERT INTO public.dm_country
    (country_code_2, country_code_3, country_name, capital, population, add_timestamp)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (country_code_2) DO UPDATE SET
    country_code_3 = EXCLUDED.country_code_3,
    country_name   = EXCLUDED.country_name,
    capital        = EXCLUDED.capital,
    population     = EXCLUDED.population,
    add_timestamp  = EXCLUDED.add_timestamp;
"""
 
 
def _fetch_country_codes(cur) -> list[str]:
    cur.execute("SELECT DISTINCT country FROM staging.bulletin_raw WHERE country IS NOT NULL")
    return [row[0] for row in cur.fetchall()]
 
 
def _eia_has_data(cur) -> bool:
    cur.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'staging'
              AND table_name   = 'eia_spothinnad_raw'
        )
    """)
    if not cur.fetchone()[0]:
        return False
    cur.execute("SELECT EXISTS (SELECT 1 FROM staging.eia_spothinnad_raw LIMIT 1)")
    return cur.fetchone()[0]
 
 
def _fetch_from_api(country_code_2: str) -> dict:
    url = f"https://restcountries.com/v3.1/alpha/{country_code_2}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()[0]
 
    return {
        "country_code_2": data.get("cca2"),
        "country_code_3": data.get("cca3"),
        "country_name":   data.get("name", {}).get("common"),
        "capital":        data.get("capital", [None])[0],
        "population":     data.get("population"),
    }
 
 
def run(hook):
    from contextlib import closing
 
    with closing(hook.get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
 
                cur.execute(CREATE_TABLE_SQL)
 
                country_codes = _fetch_country_codes(cur)
                if not country_codes:
                    print("dm_country: staging.bulletin_raw on tühi, midagi pole teha")
                    return 0
 
                # Lisa US kui eia_spothinnad_raw eksisteerib ja sisaldab andmeid
                if _eia_has_data(cur):
                    if "US" not in country_codes:
                        country_codes.append("US")
                        print("dm_country: lisatud US (eia_spothinnad_raw sisaldab andmeid)")
 
                print(f"dm_country: leitud {len(country_codes)} riiki: {country_codes}")
 
                inserted = 0
                for code in country_codes:
                    try:
                        row = _fetch_from_api(code)
                        cur.execute(UPSERT_SQL, (
                            row["country_code_2"],
                            row["country_code_3"],
                            row["country_name"],
                            row["capital"],
                            row["population"],
                        ))
                        inserted += cur.rowcount
                        print(f"  {code} → {row['country_name']} ({row['country_code_3']}), "
                              f"pealinn: {row['capital']}, rahvastik: {row['population']:,}")
                    except Exception as e:
                        print(f"  {code} → API viga: {e}")
 
                print(f"dm_country: {inserted} rida upsert-itud")
 
    return inserted