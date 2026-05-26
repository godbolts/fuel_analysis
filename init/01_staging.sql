-- Staging kihi tabelid
-- Kaivitub automaatselt Docker kaivitusel (docker-entrypoint-initdb.d)

CREATE SCHEMA IF NOT EXISTS staging;

-- EU Weekly Oil Bulletin: EE/LV/LT Euro95 ja Diesel €/l
CREATE TABLE IF NOT EXISTS staging.bulletin_raw (
    week_date      DATE        NOT NULL,
    country        TEXT        NOT NULL,
    euro95_eur_kl  NUMERIC(8,2),
    diesel_eur_kl  NUMERIC(8,2),
    loaded_at      TIMESTAMP   DEFAULT NOW(),
    PRIMARY KEY (week_date, country)
);

-- Yahoo Finance: Brent crude oil spot price
CREATE TABLE IF NOT EXISTS staging.brent_raw (
    week_date     DATE PRIMARY KEY,
    brent_usd_bbl NUMERIC(8,2),
    loaded_at     TIMESTAMP DEFAULT NOW()
);

-- EIA US Gulf Coast: bensiin ja diisel spothinnad (reede kuupaev)
CREATE TABLE IF NOT EXISTS staging.eia_spothinnad_raw (
    week_date         DATE PRIMARY KEY,
    bensiin95_usd_gal NUMERIC(8,4),
    diisel_usd_gal    NUMERIC(8,4),
    loaded_at         TIMESTAMP DEFAULT NOW()
);

-- Yahoo Finance: EUR/USD valuutakurss
CREATE TABLE IF NOT EXISTS staging.valuutakurss (
    week_date DATE PRIMARY KEY,
    eur_usd   NUMERIC(8,6),
    loaded_at TIMESTAMP DEFAULT NOW()
);

-- Yahoo Finance indikaatorid: DXY, VIX, OVX
CREATE TABLE IF NOT EXISTS staging.yahoo_indikaatorid_raw (
    week_date DATE PRIMARY KEY,
    dxy       NUMERIC(8,4),
    vix       NUMERIC(8,4),
    ovx       NUMERIC(8,4),
    loaded_at TIMESTAMP DEFAULT NOW()
);

-- GPR: paevane geopoliitiline riskiindeks
CREATE TABLE IF NOT EXISTS staging.gpr_raw (
    gpr_date  DATE PRIMARY KEY,
    gpr       NUMERIC(10,2),
    loaded_at TIMESTAMP DEFAULT NOW()
);

-- EIA US naftavarud: iganadalane tase (tuhat barrelit)
CREATE TABLE IF NOT EXISTS staging.eia_varud_raw (
    varud_date DATE PRIMARY KEY,
    eia_varud  NUMERIC(12,0),
    loaded_at  TIMESTAMP DEFAULT NOW()
);
