# Edenemisraport

## Mis on valmis

- [+] Docker Compose käivitab kõik teenused
- [+] Andmeid saadakse allikast kätte
- [+] Andmed laetakse `staging` kihti
- [+] Kõik transformatsioonid toimivad
- [+] Näidikulaud on nähtaval Supersetis
- [+] Andmekvaliteedi testid läbivad
- [+] ML hinnaennustus töötab

---

## Valmis on täielik ELT pipeline staging- ja mart-kihtidega

Docker Compose käivitab **5 konteinerit**: Airflow API server, scheduler, DAG processor, PostgreSQL metaandmebaas ja PostgreSQL/DuckDB analüütikabaas.

### Ingest — `kutuse_hind_pipeline`

Laeb andmeid **7 allikast** 7 staging tabelisse (ajakava: reede 08:00 UTC):

| Tabel | Kirjeldus | Allikas |
|---|---|---|
| `staging.bulletin_raw` | EE/LV/LT Euro95 ja diisel €/l | EU Weekly Oil Bulletin |
| `staging.brent_raw` | Brent toornafta nädala sulgemishind USD/bbl | Yahoo Finance |
| `staging.valuutakurss` | EUR/USD vahetuskurss | Yahoo Finance |
| `staging.yahoo_indikaatorid_raw` | DXY, VIX, OVX indikaatorid | Yahoo Finance |
| `staging.eia_spothinnad_raw` | US Gulf Coast bensiin ja diisel $/gal | EIA |
| `staging.eia_varud_raw` | USA toornafta varud tuh. bbl | EIA |
| `staging.gpr_raw` | Geopoliitilise riski päevane indeks | Caldara & Iacoviello |

Kõik 14 taski (7 extract + 7 load) jooksevad edukalt.

### Transform — `kutuse_transform_pipeline`

Transformeerib staging andmed **7 mart-tabelisse** (ajakava: reede 09:00 UTC):

| Tabel | Kirjeldus |
|---|---|
| `public.dm_date_aggregation` | Kalendri dimensioon |
| `public.dm_country` | Riigi dimensioon (restcountries.com API) |
| `public.ft_baltikum_prices` | EE/LV/LT kütuse jaemüügihinnad EUR/l |
| `public.ft_usa_prices` | USA kütuse spothinnad USD/l ja EUR/l + naftavarud + varude delta |
| `public.ft_brent` | Brent toornafta hind USD/l, EUR/l, USD/bbl, EUR/bbl |
| `public.ft_market` | Dollar index, S&P 500 volatiilsus, nafta volatiilsus, GPR nädala keskmised |
| `public.ft_exchange_rate` | EUR/USD ja USD/EUR kursid |

### Põhimõtted

- **ELT** — toorandmed hoitakse staging kihis muutmata kujul, teisendused toimuvad eraldi transform kihis.
- **Inkrementaalne laadimine** — mõlemad pipeline'id laevad ainult uued read alates viimasest kirjest.
- **Andmelünkade täitmine** — kui staging andmetes esineb puuduv nädal kahe eksisteeriva nädala vahel, arvutab transformatsioon lineaarse interpolatsiooniga vaheväärtuse ja lisab selle tabelisse. Iga faktitabel sisaldab veergu `is_calculated` (`TRUE` = interpoleeritud, `FALSE` = päris andmed), mis tagab analüüsi läbipaistvuse ja laseb sünteetilised andmepunktid vajadusel filtrist välja jätta.
- **Migratsiooniturvalisus** — kõik transformatsioonid tuvastavad vana skeemi automaatselt ja teevad vajadusel täieliku rebuild-i, ilma käsitsi sekkumiseta.

---

## Järgmised sammud

1. Protsessi automatiseerimine, et `docker compose up` teeks kohe käivitamisel ära kõik sammud ja visualisatsioonid ilmuksid kohe.

---

## Mis takistab

- Praegu pole blokeerivaid probleeme, on vaja lihtsalt võtta aega ja arendada.
- EIA allikad avaldavad andmeid 1–2 nädala viivitusega — see on normaalne ja ei ole viga.
- GPR indeks uueneb ~kord kuus (päevased väärtused on olemas, nädala agregeerimine tehakse transform-kihis).

---

## Kontrollpunkt

Käsud, millega saab kontrollida, et töövoog töötab:

```powershell
# Kontrolli, et staging tabelites on andmeid
$sql = "SELECT 'bulletin' AS tabel, COUNT(*) AS read, MAX(week_date) AS viimane FROM staging.bulletin_raw
UNION ALL SELECT 'brent', COUNT(*), MAX(week_date) FROM staging.brent_raw
UNION ALL SELECT 'valuutakurss', COUNT(*), MAX(week_date) FROM staging.valuutakurss
UNION ALL SELECT 'yahoo_indikaatorid', COUNT(*), MAX(week_date) FROM staging.yahoo_indikaatorid_raw
UNION ALL SELECT 'eia_spothinnad', COUNT(*), MAX(week_date) FROM staging.eia_spothinnad_raw
UNION ALL SELECT 'eia_varud', COUNT(*), MAX(varud_date) FROM staging.eia_varud_raw
UNION ALL SELECT 'gpr', COUNT(*), MAX(gpr_date) FROM staging.gpr_raw
ORDER BY tabel"
$sql | docker exec -i kutus-analytics-db psql -U bensiin -d bensiin
```

Oodatav tulemus: kõik 7 tabelit loetletud, `read` > 0 ja `viimane` on hiljutine kuupäev (mitte NULL).

```powershell
# Kontrolli, et mart tabelites on andmeid
$sql = "SELECT 'dm_date_aggregation' AS tabel, COUNT(*) AS read, MAX(week_start_date) AS viimane FROM public.dm_date_aggregation
UNION ALL SELECT 'dm_country', COUNT(*), NULL FROM public.dm_country
UNION ALL SELECT 'ft_baltikum_prices', COUNT(*), MAX(week_start_date) FROM public.ft_baltikum_prices
UNION ALL SELECT 'ft_usa_prices', COUNT(*), MAX(week_start_date) FROM public.ft_usa_prices
UNION ALL SELECT 'ft_brent', COUNT(*), MAX(week_start_date) FROM public.ft_brent
UNION ALL SELECT 'ft_market', COUNT(*), MAX(week_start_date) FROM public.ft_market
UNION ALL SELECT 'ft_exchange_rate', COUNT(*), MAX(week_start_date) FROM public.ft_exchange_rate
ORDER BY tabel"
$sql | docker exec -i kutus-analytics-db psql -U bensiin -d bensiin
```

Oodatav tulemus: kõik 7 mart-tabelit loetletud, `read` > 0 ja `viimane` on hiljutine kuupäev.
