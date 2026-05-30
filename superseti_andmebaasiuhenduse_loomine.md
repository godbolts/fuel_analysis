# Superseti ühendamine analüütikaandmebaasiga

## 1. Ava Superseti veebiliides

Ava veebibrauseris aadress:

```text
http://localhost:8088
```

## 2. Logi Supersetisse sisse

Superseti administraatori kasutaja luuakse teenuse `superset-init` käivitamisel `.env` failis olevate väärtuste põhjal:

```env
SUPERSET_ADMIN_USER=...
SUPERSET_ADMIN_PASSWORD=...
SUPERSET_ADMIN_EMAIL=...
```

Kasuta sisselogimiseks `.env` failis määratud administraatori kasutajanime ja parooli.

## 3. Alusta andmebaasiühenduse loomist

Pärast sisselogimist vali Supersetis:

```text
Settings → Database Connections → + Database
```

Vali andmebaasi tüübiks **PostgreSQL**.

## 4. Täida ühenduse andmed

Sisesta andmebaasiühenduse väljadele järgmised väärtused:

| Väli | Väärtus |
|---|---|
| Host | `analytics-db` |
| Port | `5432` |
| Database name | `.env` failist: `POSTGRES_DB`=... |
| Username | `.env` failist: `POSTGRES_USER`=... |
| Password | `.env` failist: `POSTGRES_PASSWORD`=... |

## 5. Loo ühendus

Klõpsa nuppu **Connect**.

Kui ühenduse andmed on õiged ja andmebaasi konteiner töötab, peaks Superset kuvama teate:

```text
Database connected
```

## 6. Lõpeta seadistamine

Vajuta **Finish**.

Andmebaasiühendus on nüüd loodud ning järgmise sammuna saab Supersetis lisada vajalikud tabelid dataset'idena ja hakata nende põhjal visualiseeringuid looma.
