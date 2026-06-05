"""
public.ft_price_forecast
-------------------------
Allikas: public.ft_baltikum_prices + public.ft_brent
Loogika: Ridge regression — EE tankladiisli hinnaennustus
  Features:
    - brent_lag3/4/5 : Brenti hind 3/4/5 nädalat enne (lag=3 korrelatsiooni tipp 0.91)
    - prev_price      : eelmise nädala EE diisel
    - rolling_4wk     : 4-nädala libisev keskmine
  Iga jooksul kustutatakse EE read ja kirjutatakse uuesti:
    - ajaloolised read: actual_price + forecast_price (in-sample fit), is_forecast=FALSE
    - tuleviku 8 nädalat: ainult forecast_price, is_forecast=TRUE
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ft_price_forecast (
    week_start_date   DATE          NOT NULL,
    country_code      CHAR(2)       NOT NULL,
    actual_price      NUMERIC(6,3),
    forecast_price    NUMERIC(6,3)  NOT NULL,
    forecast_lower    NUMERIC(6,3),
    forecast_upper    NUMERIC(6,3),
    is_forecast       BOOLEAN       NOT NULL,
    generated_at      TIMESTAMPTZ   NOT NULL,
    PRIMARY KEY (week_start_date, country_code)
);
"""

FEATURES = ["brent_lag3", "brent_lag4", "brent_lag5", "prev_price", "rolling_4wk"]


def _load_data(hook, country_code: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Laeb ühe riigi hinnad ja Brenti DB-st."""
    conn = hook.get_conn()
    df_prices = pd.read_sql_query(
        "SELECT week_start_date, diesel_price FROM public.ft_baltikum_prices "
        f"WHERE country_code = '{country_code}' ORDER BY week_start_date",
        conn,
    )
    df_brent = pd.read_sql_query(
        "SELECT week_start_date AS brent_date, eur_l AS brent_price "
        "FROM public.ft_brent ORDER BY week_start_date",
        conn,
    )
    conn.close()
    df_prices["week_start_date"] = pd.to_datetime(df_prices["week_start_date"])
    df_brent["brent_date"] = pd.to_datetime(df_brent["brent_date"])
    return df_prices, df_brent


def _build_features(df_prices: pd.DataFrame, df_brent: pd.DataFrame) -> pd.DataFrame:
    """Lisab feature veerud: brent_lag3/4/5, prev_price, rolling_4wk."""
    df = df_prices.copy().sort_values("week_start_date").reset_index(drop=True)

    for lag in [3, 4, 5]:
        shifted = df_brent.copy()
        shifted["week_start_date"] = shifted["brent_date"] + pd.Timedelta(weeks=lag)
        shifted = shifted.rename(columns={"brent_price": f"brent_lag{lag}"})[
            ["week_start_date", f"brent_lag{lag}"]
        ]
        df = df.merge(shifted, on="week_start_date", how="left")

    df["prev_price"] = df["diesel_price"].shift(1)
    df["rolling_4wk"] = df["diesel_price"].shift(1).rolling(4).mean()
    return df


def _get_brent_for_date(target_date: pd.Timestamp, df_brent: pd.DataFrame) -> float:
    """Tagastab lähima Brenti hinna kuupäevale (kasutab viimast kui pole täpset vastet)."""
    row = df_brent[df_brent["brent_date"] == target_date]
    if not row.empty:
        return float(row["brent_price"].values[0])
    return float(df_brent["brent_price"].iloc[-1])


def run(hook) -> int:
    # 1. Tabel
    conn = hook.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.ft_price_forecast')")
    if cur.fetchone()[0] is None:
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()

    insert_sql = """
        INSERT INTO public.ft_price_forecast
            (week_start_date, country_code, actual_price, forecast_price,
             forecast_lower, forecast_upper, is_forecast, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    total_inserted = 0
    now = pd.Timestamp.utcnow()

    for country_code in ["EE", "LV", "LT"]:
        # 2. Andmed + features
        df_prices, df_brent = _load_data(hook, country_code)
        df = _build_features(df_prices, df_brent)

        # 3. Treeniandmed (read kus kõik featurid olemas)
        df_train = df.dropna(subset=FEATURES + ["diesel_price"]).copy()
        X = df_train[FEATURES].values
        y = df_train["diesel_price"].values.astype(float)

        # 4. Mudel
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        model.fit(X, y)

        y_fitted = model.predict(X)
        residual_std = float(np.std(y - y_fitted))

        df_train["forecast_price"] = np.round(y_fitted, 3)
        df_train["is_forecast"] = False

        # 5. Tulevik: 8 nädalat
        last_date = df["week_start_date"].max()
        rolling_window = list(df.tail(4)["diesel_price"].values.astype(float))
        prev = float(df.loc[df["week_start_date"] == last_date, "diesel_price"].values[0])

        future_rows: list[dict] = []
        for i in range(1, 9):
            future_date = last_date + pd.Timedelta(weeks=i)
            feat = np.array([[
                _get_brent_for_date(future_date - pd.Timedelta(weeks=3), df_brent),
                _get_brent_for_date(future_date - pd.Timedelta(weeks=4), df_brent),
                _get_brent_for_date(future_date - pd.Timedelta(weeks=5), df_brent),
                prev,
                float(np.mean(rolling_window[-4:])),
            ]])
            pred = float(np.round(model.predict(feat)[0], 3))
            future_rows.append({
                "week_start_date": future_date.date(),
                "forecast_price": pred,
                "is_forecast": True,
            })
            rolling_window.append(pred)
            prev = pred

        # 6. Kirjuta DB-sse
        cur.execute(f"DELETE FROM public.ft_price_forecast WHERE country_code = '{country_code}'")

        inserted = 0
        for _, row in df_train.iterrows():
            fp = float(row["forecast_price"])
            cur.execute(insert_sql, (
                row["week_start_date"].date(), country_code,
                float(row["diesel_price"]), fp,
                round(fp - 2 * residual_std, 3),
                round(fp + 2 * residual_std, 3),
                False, now,
            ))
            inserted += 1

        for row in future_rows:
            fp = row["forecast_price"]
            cur.execute(insert_sql, (
                row["week_start_date"], country_code,
                None, fp,
                round(fp - 2 * residual_std, 3),
                round(fp + 2 * residual_std, 3),
                True, now,
            ))
            inserted += 1

        conn.commit()
        r2 = float(np.corrcoef(y, y_fitted)[0, 1] ** 2)
        print(f"  {country_code} Ridge R²: {r2:.4f} | residual_std: {residual_std:.4f} | {inserted} rida")
        total_inserted += inserted

    cur.close()
    return total_inserted
