import pandas as pd
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from typing import Dict
import metrics

# =========================
# CONFIGURATION
# =========================

"""
Expected Format:
- TIME:  Timestamp of the request - string.
- ROUTE: Route of the request.
- VALUE: Latency in ms.
"""
DATA_PATH = "../data/log_nav_2026.csv"

RESOLUTION_MAP: Dict[str, str] = {
    "1min":  "1min",
    "5min":  "5min",
    "10min": "10min",
    "25min": "25min",
    "60min": "60min",
    "1day":  "1D"
}

# =========================
# LOAD DATA
# =========================

df_raw = pd.read_csv(DATA_PATH)

df_raw['TIME'] = pd.to_datetime(
    df_raw['TIME'],
    format="%Y-%m-%dT%H:%M:%S",
    errors="coerce"
)
df_raw = df_raw.sort_values('TIME')

# =========================
# PRECOMPUTE BASE
# =========================

BASE_1MIN = metrics.build_base_1min(df_raw)

# =========================
# FASTAPI
# =========================

app = FastAPI(title="Latency System API")

@app.get("/")
def root():
    return FileResponse("view/viz.html")


@app.get("/docs")
def docs():
    return {
        "message": "Latency system API",
        "endpoint": "/system/resolution?resolution=1min"
    }

@app.get("/system/resolution")
def system_resolution(
    resolution: str = Query("1min", description="Time resolution")
):
    if resolution not in RESOLUTION_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resolution. Options: {list(RESOLUTION_MAP.keys())}"
        )

    target_res = RESOLUTION_MAP[resolution]

    base_resampled = metrics.convert_resolution(BASE_1MIN, target_res)
    system_df = metrics.compute_system_stats(base_resampled)
    system_df = metrics.sanitize(system_df)

    return {
        "resolution": resolution,
        "count": len(system_df),
        "data": system_df.to_dict(orient="records")
    }


@app.get("/health")
def health():
    return {"status": "ok"}

