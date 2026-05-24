# Arhitektuur

## Äriküsimus

Kui kiiresti ja võrdselt kanduvad bensiini/diisli hinnamuutused üle Baltikumi tankla hindadesse ning milline riik pakub igal nädalal odavaima kütuse?

## Mõõdikud

1. Maailma bensiini ja Eesti, Läti, Leedu hinnavõrdlus nädala lõikes
2. Maailma diisli ja Eesti, Läti, Leedu hinnavõrdlus nädala lõikes

## Andmeallikad

| Allikas | Tüüp | Ajas muutuv? | Roll | Link |
|---------|------|--------------|------|------|
| European Weekly Oil Bulletin | xlsx | Kord nädalas (Neljapäevit) | Baltikumide hinnad | https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx |
| Oil Price | JSON | 5 minutit | Maailma hinnad | https://www.oilpriceapi.com |
| US Statistics | XLS | päevas/nädalas/kuus | Maailma/USA hinnad | https://www.eia.gov/opendata/, https://www.eia.gov/dnav/pet/pet_pri_spt_s1_w.htm, https://www.eia.gov/dnav/pet/xls/PET_PRI_SPT_S1_W.xls |
| Yahoo Finance | JSON | Kord nädalas (Reede) | Euro ja dollari kurss | https://query1.finance.yahoo.com/v8/finance/chart/EURUSD%3DX?interval=1wk&range=5y |
| Teadmiseks | JSON | Päevas | Tallinna kütusehinnad | https://teadmiseks.ee/wp-content/themes/Total/fuel-chart-30d.php |

## Andmevoog

```mermaid
flowchart LR

    subgraph Sources["Andmeallikad"]

        subgraph Weekly["Nädalased allikad"]
            eu[European Weekly Oil Bulletin<br/>XLSX<br/>Neljapäev]
            yahoo[Yahoo Finance EUR/USD<br/>JSON<br/>Reede]
        end

        subgraph Frequent["Sagedased allikad"]
            oil[OilPrice API<br/>JSON<br/>5 min]
            teadmiseks[Teadmiseks.ee<br/>JSON<br/>Päev]
        end

        subgraph Statistical["Statistilised allikad"]
            eia[US EIA Statistics<br/>XLS/XLSX/API<br/>Päev/Nädal/Kuu]
        end
    end

    subgraph Ingestion["Sissevõtt"]
        api[API Connector]
        file[File Loader]
        scheduler[Scheduler]
    end

    subgraph Storage["Andmeladu"]
        staging[(staging)]
        transform[Transformatsioon]
        mart[(mart)]
    end

    subgraph Consumption["Tarbimine"]
        dashboard[Näidikulaud]
        quality[Andmekvaliteedi testid]
        alerts[Hinnamuutuste teavitused]
    end

    eu --> file
    eia --> file

    oil --> api
    yahoo --> api
    teadmiseks --> api
    eia --> api

    scheduler --> api
    scheduler --> file

    api --> staging
    file --> staging

    staging --> transform
    transform --> mart

    mart --> dashboard
    mart --> quality
```

## Andmebaasi kihid

| Kiht | Roll |
|------|------|
| `staging` | Hoiab allika andmeid töötlemata kujul. |
| `mart` | Hoiab transformeeritud ja ärilogikat sisaldavaid tabeleid. |

## Tööjaotus

| Roll | Vastutus | Täitja |
|------|----------|--------|
| Andmeallika omanik | Kirjutab sissevõtu loogika, hoiab API-t töös | Üllar |
| Transformatsioonide omanik | Kirjutab mart kihi mudelid ja mõõdikute arvutuse | Marko |
| Kvaliteedi omanik | Kirjutab testid ja vaatab läbi ebaõnnestunud kontrollid | Jürgen |
| Näidikulaua omanik | Ehitab näidikulaua ja seob selle äriküsimusega | Teet |

## Riskid

| Risk | Mõju | Maandus |
|------|------|---------|
| API ei vasta | Andmed ei uuene | Programmeerime töövoo teatud aja tagant uuesti proovima. Logime API ühenduse katsed. Kui on pikem katkestus, siis saadame teate. |
| Andmeallika failis on muudatus andmestruktuuris | Võib lõhkuda töövoo, kui sobivat välja päring ei leia. | Testime andmeallika väljade kattuvust. Logime tulemused. Saadame teate, kui töövoog katkeb. |
| Andmeallika failis on andmed puudu | Andmed ei uuene või näitavad valesid tulemusi. | Testime andmete kvaliteeti. Logime tulemused. Saadame teate vigade korral. |

## Privaatsus ja turve

Meie projektis on kasutusel avalikud andmed, ja ei ole tegemist ei isiku ega turvet vajavate andmetega.
