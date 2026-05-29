# Baltikumi Kütusehindade Analüüsi Projekt

## Käivitamine

Kui oled projekti pullinud, käivita:

```bash
docker compose up -d
```

Docker tõmbab vajalikud image-id ja ehitab konteinerid üles automaatselt. Esimesel käivitamisel kulub see mõni minut.

Kui logi kirjed hakkavad konstantselt korduma, on programm **idle** olekus — see on normaalne. Kuigi kõik konteinerid on üleval ja tabelid on loodud, on need tühjad, kuna pipeline'id ootavad täpset käivitamisaega (ingest reedeti kell 08:00, transform reedeti kell 09:00).

**Kõige lihtsam viis andmeid kohe laadida** on minna brauseris aadressile `http://localhost:8080`, logida sisse `.env` failis olevate paroolidega ja käivitada DAG-id käsitsi:

1. Logi sisse Airflow UI-sse
2. Vali DAG-ide nimekirjast `kutuse_hind_pipeline`
3. Vajuta ▶ (Trigger DAG) ja oota kuni kõik taskid on rohelised
4. Seejärel käivita samamoodi `kutuse_transform_pipeline`

---

## Andmebaasi struktuur

Andmebaas on jagatud kahte skeemi:

- **`staging`** — toorandmed, laaditud otse allikatest, muutmata kujul
- **`public`** — transformeeritud mart-kihis tabelid, analüüsiks valmis

---

## Mart-kihis tabelid

### `public.dm_country`

Dimensioonitabel kõigi andmestikus esinevate riikide kohta.

| Veerg | Tüüp | Kirjeldus |
|---|---|---|
| `country_code_2` | CHAR(2) | Kahetäheline riigikood (PK) — join-veerg teiste tabelitega |
| `country_code_3` | CHAR(3) | Kolmetäheline riigikood |
| `country_name` | VARCHAR(100) | Riigi nimi inglise keeles |
| `capital` | VARCHAR(100) | Pealinna nimi |
| `population` | BIGINT | Rahvaarv |
| `add_timestamp` | TIMESTAMPTZ | Viimase upsert-i aeg |

**Loogika:** Riigikoodid loetakse `staging.bulletin_raw` tabelist (EE, LV, LT). Kui `staging.eia_spothinnad_raw` tabel eksisteerib ja sisaldab andmeid, lisatakse automaatselt ka `US`. Riigi metaandmed (nimi, pealinn, rahvaarv) päritakse [restcountries.com](https://restcountries.com) API-st. Tabel upsert-itakse igal joomisel, kuna rahvaarv võib ajas muutuda.

---

### `public.ft_baltikum_prices`

Eesti, Läti ja Leedu iganädalased kütusejaamahinnad eurodes liitri kohta.

| Veerg | Tüüp | Kirjeldus |
|---|---|---|
| `week_start_date` | DATE | Nädala alguskuupäev (esmaspäev) — PK osa |
| `country_code` | CHAR(2) | Kahetäheline riigikood (EE/LV/LT) — PK osa, join `dm_country`-ga |
| `petrol_price` | NUMERIC(6,3) | Euro 95 bensiini hind EUR/l |
| `diesel_price` | NUMERIC(6,3) | Diislikütuse hind EUR/l |
| `add_timestamp` | TIMESTAMPTZ | Kirje lisamise aeg |

**Allikas:** EU Weekly Oil Bulletin (`staging.bulletin_raw`). Algsed väärtused on EUR/1000l, teisendatud EUR/l-ks (`/ 1000`).

---

### `public.ft_usa_prices`

USA iganädalased kütuse spothinnad, teisendatud USD/gallonist USD/liitriks ja EUR/liitriks.

| Veerg | Tüüp | Kirjeldus |
|---|---|---|
| `week_start_date` | DATE | Nädala alguskuupäev — PK osa |
| `country_code` | CHAR(2) | Alati `US` — PK osa, join `dm_country`-ga |
| `petrol_usd_l` | NUMERIC(6,4) | Bensiini hind USD/l |
| `diesel_usd_l` | NUMERIC(6,4) | Diisli hind USD/l |
| `petrol_eur_l` | NUMERIC(6,4) | Bensiini hind EUR/l (jagatud EUR/USD kursiga) |
| `diesel_eur_l` | NUMERIC(6,4) | Diisli hind EUR/l (jagatud EUR/USD kursiga) |
| `eur_usd_rate` | NUMERIC(8,6) | Sel nädalal kasutatud EUR/USD kurss |
| `add_timestamp` | TIMESTAMPTZ | Kirje lisamise aeg |

**Allikas:** EIA US Gulf Coast spothinnad (`staging.eia_spothinnad_raw`). Teisendus: `USD/gallon ÷ 3.78541 = USD/liiter`. EUR/l saadakse jagamisel EUR/USD kursiga (`staging.valuutakurss`), join toimub nädala alguskuupäeva järgi.

---

### `public.ft_exchange_rate`

Iganädalane EUR/USD valuutakurss mõlemas suunas.

| Veerg | Tüüp | Kirjeldus |
|---|---|---|
| `week_start_date` | DATE | Nädala alguskuupäev (PK) |
| `eur_usd` | NUMERIC(8,6) | 1 EUR = X USD |
| `usd_eur` | NUMERIC(8,6) | 1 USD = X EUR (arvutuslik: `1 / eur_usd`) |
| `add_timestamp` | TIMESTAMPTZ | Kirje lisamise aeg |

**Allikas:** Yahoo Finance EUR/USD nädalaandmed (`staging.valuutakurss`).

---

## Tabelite seosed

```
dm_country (country_code_2)
    ├── ft_baltikum_prices.country_code
    └── ft_usa_prices.country_code

ft_exchange_rate (week_start_date)
    └── ft_usa_prices.week_start_date  [kasutatud EUR teisenduseks]
```
