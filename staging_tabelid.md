# Staging tabelite kirjeldus

Kõik staging tabelid sisaldavad **toorandmeid**, täpselt nii nagu allikast tulevad, teisendusi pole.
Kõik teisendused toimuvad SQL transform-kihis (`fuel_analysis/transforms/`).

---

## `staging.bulletin_raw`

**Allikas:** EU Weekly Oil Bulletin (Euroopa Komisjon) | **Uueneb:** neljapäeviti

| Veerg           | Tüüp         | Kirjeldus                               | Vajalik tegevus          |
|-----------------|--------------|-----------------------------------------|--------------------------|
| `week_date`     | DATE         | Nädala kuupäev (esmaspäev)              | Juba ok                  |
| `country`       | TEXT         | Riigi kood: EE, LV või LT               | Juba ok                  |
| `euro95_eur_kl` | NUMERIC(8,2) | Euro95 jaehind koos maksudega (€/1000L) | Teisenda €/l             |
| `diesel_eur_kl` | NUMERIC(8,2) | Diisel jaehind koos maksudega (€/1000L) | Teisenda €/l             |

---

## `staging.brent_raw`

**Allikas:** Yahoo Finance (BZ=F) | **Uueneb:** börsipäeviti, pipeline tõmbab nädala sulgemishinna

| Veerg           | Tüüp         | Kirjeldus                              | Vajalik tegevus           |
|-----------------|--------------|----------------------------------------|---------------------------|
| `week_date`     | DATE         | Nädala kuupäev (esmaspäev)             | Juba ok                   |
| `brent_usd_bbl` | NUMERIC(8,2) | Brent toornafta sulgemishind (USD/bbl) | Teisenda €/l              |

> `eur_usd` tuleb `staging.valuutakurss` tabelist (JOIN `week_date` järgi). 158.987 = liitrit ühes barrelis.

---

## `staging.valuutakurss`

**Allikas:** Yahoo Finance (EURUSD=X) | **Uueneb:** börsipäeviti, pipeline tõmbab nädala sulgemiskursi

| Veerg       | Tüüp         | Kirjeldus                                 | Vajalik tegevus                       |
|-------------|--------------|-------------------------------------------|---------------------------------------|
| `week_date` | DATE         | Nädala kuupäev (esmaspäev)                | Juba ok                               |
| `eur_usd`   | NUMERIC(8,6) | Vahetuskurss: USD ühe EUR eest            | Kasuta teiste tabelite konversiooniks |

---

## `staging.yahoo_indikaatorid_raw`

**Allikas:** Yahoo Finance (DX-Y.NYB, ^VIX, ^OVX) | **Uueneb:** börsipäeviti, pipeline tõmbab nädala sulgemishinna

| Veerg       | Tüüp         | Kirjeldus                                                              | Vajalik tegevus |
|-------------|--------------|------------------------------------------------------------------------|-----------------|
| `week_date` | DATE         | Nädala kuupäev (esmaspäev)                                             | Juba ok         |
| `dxy`       | NUMERIC(8,4) | USA dollariindeks (USD tugevus vs teised valuutad EUR/JPY/GBP jt)      | Otse mart-i     |
| `vix`       | NUMERIC(8,4) | S&P 500 volatiilsusindeks (turu hirmuindeks)                           | Otse mart-i     |
| `ovx`       | NUMERIC(8,4) | Nafta volatiilsusindeks (naftaturgu spetsiifiline VIX)                 | Otse mart-i     |

---

## `staging.eia_spothinnad_raw`

**Allikas:** EIA US Gulf Coast (PET_PRI_SPT_S1_W) | **Uueneb:** esmaspäeviti (~1-2 nädala viivitus)

| Veerg               | Tüüp         | Kirjeldus                                       | Vajalik tegevus                           |
|---------------------|--------------|-------------------------------------------------|-------------------------------------------|
| `week_date`         | DATE         | EIA raporteerimiskuupäev (reede)                | Konverteeri esmaspäeva kuupäevaks         |
| `bensiin95_usd_gal` | NUMERIC(8,4) | Bensiin95 spothind (USD/gallon)                 | Teisenda €/l                              |
| `diisel_usd_gal`    | NUMERIC(8,4) | Diisel (ULSD) spothind (USD/gallon)             | Teisenda €/l                              |

> `eur_usd` tuleb `staging.valuutakurss` tabelist. 3.78541 = liitrit ühes USA gallonis.

---

## `staging.eia_varud_raw`

**Allikas:** EIA USA toornafta nädalased varud (WCRSTUS1) | **Uueneb:** kolmapäeviti

| Veerg        | Tüüp          | Kirjeldus                                          | Vajalik tegevus                                    |
|--------------|---------------|----------------------------------------------------|----------------------------------------------------|
| `varud_date` | DATE          | EIA nädala lõppkuupäev (reede)                     | Konverteeri esmaspäeva kuupäevaks                  |
| `eia_varud`  | NUMERIC(12,0) | USA toornafta kogus kaubandusvarudes (tuhat bbl)   | Tõenäoliselt vaja analüüsiks nädalane muutus leida |

> Negatiivne muutus = varud vähenesid = nõudlus > pakkumine → Brent tõuseb.

---

## `staging.gpr_raw`

**Allikas:** Caldara & Iacoviello geopoliitilise riski indeks | **Uueneb:** ~kord kuus

| Veerg      | Tüüp          | Kirjeldus                                                 | Vajalik tegevus                                 |
|------------|---------------|-----------------------------------------------------------|-------------------------------------------------|
| `gpr_date` | DATE          | Päevane kuupäev                                           | Konverteeri esmaspäeva kuupäevaks               |
| `gpr`      | NUMERIC(10,2) | Geopoliitilise riski indeks (norm ~100, kriisi ajal >200) | Kuna päevane data, vaja leida nädala keskmine   |

---

## Testimine – mis data on tabelites

Käivita PowerShellis (Docker peab töötama):

```powershell
$sql = "SELECT * FROM staging.bulletin_raw ORDER BY week_date DESC LIMIT 3"; $sql | docker exec -i kutus-analytics-db psql -U bensiin -d bensiin
$sql = "SELECT * FROM staging.brent_raw ORDER BY week_date DESC LIMIT 3"; $sql | docker exec -i kutus-analytics-db psql -U bensiin -d bensiin
$sql = "SELECT * FROM staging.valuutakurss ORDER BY week_date DESC LIMIT 3"; $sql | docker exec -i kutus-analytics-db psql -U bensiin -d bensiin
$sql = "SELECT * FROM staging.yahoo_indikaatorid_raw ORDER BY week_date DESC LIMIT 3"; $sql | docker exec -i kutus-analytics-db psql -U bensiin -d bensiin
$sql = "SELECT * FROM staging.eia_spothinnad_raw ORDER BY week_date DESC LIMIT 3"; $sql | docker exec -i kutus-analytics-db psql -U bensiin -d bensiin
$sql = "SELECT * FROM staging.eia_varud_raw ORDER BY varud_date DESC LIMIT 3"; $sql | docker exec -i kutus-analytics-db psql -U bensiin -d bensiin
$sql = "SELECT * FROM staging.gpr_raw ORDER BY gpr_date DESC LIMIT 3"; $sql | docker exec -i kutus-analytics-db psql -U bensiin -d bensiin
```

Ridade kokkuvõte kõigist tabelitest korraga:

```powershell
$sql = "SELECT 'bulletin' AS tabel, COUNT(*), MIN(week_date), MAX(week_date) FROM staging.bulletin_raw UNION ALL SELECT 'brent', COUNT(*), MIN(week_date), MAX(week_date) FROM staging.brent_raw UNION ALL SELECT 'valuutakurss', COUNT(*), MIN(week_date), MAX(week_date) FROM staging.valuutakurss UNION ALL SELECT 'yahoo', COUNT(*), MIN(week_date), MAX(week_date) FROM staging.yahoo_indikaatorid_raw UNION ALL SELECT 'eia_spot', COUNT(*), MIN(week_date), MAX(week_date) FROM staging.eia_spothinnad_raw UNION ALL SELECT 'eia_varud', COUNT(*), MIN(varud_date), MAX(varud_date) FROM staging.eia_varud_raw UNION ALL SELECT 'gpr', COUNT(*), MIN(gpr_date), MAX(gpr_date) FROM staging.gpr_raw ORDER BY 1"; $sql | docker exec -i kutus-analytics-db psql -U bensiin -d bensiin
```

