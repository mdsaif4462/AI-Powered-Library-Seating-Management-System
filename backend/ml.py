"""Machine-learning helpers: occupancy forecasting, no-show prediction, seat ranking."""
import os
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
OCC_PATH = os.path.join(MODEL_DIR, "occupancy.joblib")
NS_PATH = os.path.join(MODEL_DIR, "noshow.joblib")
OCC_FEATURES = ["hour", "day_of_week", "is_weekend", "is_exam_period"]
NS_FEATURES = ["lead_hours", "start_hour", "day_of_week", "duration",
               "past_bookings", "past_no_show_rate"]
_cache = {}


def is_exam_period(d):
    return int(d.month in (5, 12))


def _load(path):
    if path not in _cache and os.path.exists(path):
        _cache[path] = joblib.load(path)
    return _cache.get(path)


def _save(model, path):
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, path)
    _cache.clear()


# ---------------------------------------------------------------- occupancy
def synthetic_occupancy(days=180, total=60, open_hour=8, close_hour=21, seed=42):
    """Realistic fake history so the model works before real data exists."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=date.today() - timedelta(days=1), periods=days)
    df = pd.MultiIndex.from_product(
        [dates, range(open_hour, close_hour)], names=["record_date", "hour"]
    ).to_frame(index=False)
    df["day_of_week"] = df["record_date"].dt.dayofweek
    df["is_exam_period"] = df["record_date"].dt.month.isin([5, 12]).astype(int)
    curve = np.exp(-((df["hour"] - 14) ** 2) / (2 * 3.5 ** 2))
    base = 0.2 + 0.6 * curve
    base = base * np.where(df["day_of_week"] >= 5, 0.6, 1.0)
    base = base * np.where(df["is_exam_period"] == 1, 1.3, 1.0)
    base = np.clip(base + rng.normal(0, 0.05, len(df)), 0.02, 1.0)
    df["occupied"] = (base * total).round().astype(int)
    df["total_seats"] = total
    df["record_date"] = df["record_date"].dt.date
    return df


def train_occupancy(df):
    df = df.copy()
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    X, y = df[OCC_FEATURES], df["occupied"] / df["total_seats"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
    model = RandomForestRegressor(n_estimators=200, min_samples_leaf=3,
                                  random_state=42, n_jobs=-1)
    model.fit(X_tr, y_tr)
    mae = mean_absolute_error(y_te, model.predict(X_te))
    model.fit(X, y)  # refit on everything
    _save(model, OCC_PATH)
    return {"model": "occupancy", "rows": len(df), "mae_pct_points": round(mae * 100, 2)}


def forecast(day, open_hour, close_hour):
    """Predicted occupancy (%) for each opening hour of `day`."""
    hours = np.arange(open_hour, close_hour)
    X = pd.DataFrame({
        "hour": hours,
        "day_of_week": day.weekday(),
        "is_weekend": int(day.weekday() >= 5),
        "is_exam_period": is_exam_period(day),
    })
    model = _load(OCC_PATH)
    if model is None:  # fallback heuristic when no model is trained yet
        preds = 0.2 + 0.6 * np.exp(-((hours - 14) ** 2) / (2 * 3.5 ** 2))
    else:
        preds = model.predict(X[OCC_FEATURES])
    preds = np.clip(preds, 0, 1)
    return [{"hour": int(h), "occupancy": round(float(p) * 100, 1)}
            for h, p in zip(hours, preds)]


# ------------------------------------------------------------------ no-show
def synthetic_noshow(n=3000, seed=7):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "lead_hours": np.clip(rng.exponential(24, n), 0.5, 168),
        "start_hour": rng.integers(8, 20, n),
        "day_of_week": rng.integers(0, 7, n),
        "duration": rng.integers(1, 5, n),
        "past_bookings": rng.integers(0, 40, n),
        "past_no_show_rate": rng.beta(1.5, 12, n),
    })
    logit = (-2.6 + 0.018 * df["lead_hours"] + 0.15 * (df["duration"] - 2)
             + 4.0 * df["past_no_show_rate"] + 0.25 * (df["start_hour"] < 10)
             + 0.2 * (df["day_of_week"] >= 5))
    df["y"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df


def build_noshow_frame(rows):
    """Turn finished bookings (list of dicts from MySQL) into a training frame."""
    df = pd.DataFrame(rows)
    if len(df) < 300:
        return None
    df["y"] = (df["status"] == "no_show").astype(int)
    start_dt = pd.to_datetime(df["booking_date"]) + pd.to_timedelta(df["start_hour"], unit="h")
    df["lead_hours"] = ((start_dt - pd.to_datetime(df["created_at"]))
                        .dt.total_seconds() / 3600).clip(lower=0)
    df["day_of_week"] = start_dt.dt.dayofweek
    df["duration"] = df["end_hour"] - df["start_hour"]
    grp = df.groupby("user_id")
    df["past_bookings"] = grp.cumcount()
    prev_ns = grp["y"].cumsum() - df["y"]
    df["past_no_show_rate"] = (prev_ns / df["past_bookings"].replace(0, np.nan)).fillna(0)
    return df


def train_noshow(df=None):
    source = "real bookings"
    if df is None:
        df, source = synthetic_noshow(), "synthetic data"
    X, y = df[NS_FEATURES], df["y"]
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    info = {"model": "no_show", "rows": len(df), "source": source}
    if y.nunique() > 1:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y)
        model.fit(X_tr, y_tr)
        info["auc"] = round(roc_auc_score(y_te, model.predict_proba(X_te)[:, 1]), 3)
    model.fit(X, y)
    _save(model, NS_PATH)
    return info


def predict_noshow(lead_hours, start_hour, day_of_week, duration,
                   past_bookings, past_no_show_rate):
    model = _load(NS_PATH)
    if model is None:
        return 0.15
    X = pd.DataFrame([[lead_hours, start_hour, day_of_week, duration,
                       past_bookings, past_no_show_rate]], columns=NS_FEATURES)
    return float(model.predict_proba(X)[0, 1])


# ------------------------------------------------------------ seat ranking
def rank_seats(seats, prefs, zone_load, top=5):
    """Score available seats by user preferences, preferring quieter zones."""
    df = pd.DataFrame(seats)
    if df.empty:
        return []
    weights = np.array([3.0 * prefs.get("power", 0),
                        2.0 * prefs.get("window", 0),
                        2.0 * prefs.get("quiet", 0)])
    attrs = df[["has_power", "near_window", "is_quiet"]].to_numpy(dtype=float)
    load = df["zone"].map(zone_load).fillna(0.5).to_numpy(dtype=float)
    df["score"] = attrs @ weights + (1.0 - load)
    return df.sort_values(["score", "id"], ascending=[False, True]).head(top)["id"].tolist()
