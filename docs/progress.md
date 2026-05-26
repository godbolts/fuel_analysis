# Edenemisraport

> **Juhend:** See fail on projektitöö teise nädala väljund. Uuenda lühidalt iga esitamise eel. Kustuta see juhendrida.

## Mis on valmis

- [+] Docker Compose käivitab kõik teenused
- [+] Andmeid saadakse allikast kätte
- [+] Andmed laetakse `staging` kihti
- [ ] Vähemalt üks transformatsioon toimib
- [ ] Vähemalt üks näidikulaud on nähtaval
- [ ] Vähemalt üks andmekvaliteedi test läbib

**Valmis on täielik extract + load pipeline:**
- Docker Compose käivitab 4 konteinerit: Airflow webserver, scheduler, API server + PostgreSQL analüütikabaas
- Airflow DAG `kutuse_hind_pipeline` laeb andmeid **7 allikast** 7 staging tabelisse:
  - `staging.bulletin_raw` — EE/LV/LT Euro95 ja diisel €/l (EU Weekly Oil Bulletin)
  - `staging.brent_raw` — Brent toornafta nädala sulgemishind USD/bbl (Yahoo Finance)
  - `staging.valuutakurss` — EUR/USD vahetuskurss (Yahoo Finance)
  - `staging.yahoo_indikaatorid_raw` — DXY, VIX, OVX indikaatorid (Yahoo Finance)
  - `staging.eia_spothinnad_raw` — US Gulf Coast bensiin ja diisel $/gal (EIA)
  - `staging.eia_varud_raw` — USA toornafta varud tuh. bbl (EIA)
  - `staging.gpr_raw` — Geopoliitilise riski päevane indeks (Caldara & Iacoviello)
- Kõik 14 Airflow task-i (7 extract + 7 load) jooksevad edukalt
- Inkrementaalne laadimine, laeb ainult uued read alates viimasest kirjest
- Andmed on toorandmed (ELT põhimõte), kus staging kihis teisendusi pole
- Ajakava: iga reede 08:00 UTC

## Järgmised sammud

1. **SQL transform kiht** (`fuel_analysis/transforms/`) — Bulletin €/1000L → €/l; Brent USD/bbl → EUR/l; GPR päevased → nädala keskmised; kõigi allikate JOIN ühte laia tabelisse
- [Teine tegevus]
- [Kolmas tegevus]

## Mis takistab

- Praegu pole blokeerivaid probleeme
- EIA allikad avaldavad andmeid 1–2 nädala viivitusega, mis on normaalne, see ei ole mitte viga
- GPR indeks uueneb ~kord kuus (päevased väärtused olemas, nädala agregeerimine tehakse transform-kihis)

## Kontrollpunkt

Käsk, millega saab kontrollida, et töövoog töötab:

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

Oodatav tulemus: kõik 7 tabelit on loetletud, `read` > 0 ja `viimane` on hiljutine kuupäev (mitte NULL).
