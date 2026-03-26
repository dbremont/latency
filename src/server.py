"""
OUR DATA HAS SOME ISSUES: IF A USER CANCELS A REQUEST (LET'S SAY IT'S TAKING TOO LONG) - WE DON'T CAPTURE THAT REQUEST - THE END PART OF IT.

- We want to reconstruct the theoretical latency: for a random route, what latency should we expect?
- We need to account for the workload.
- We need a mechanism to analyze system behavior at time t.

Data format:

1. TIME
2. ROUTE
3. DURATION (Milliseconds)

Goal: produce a system-wide aggregation across multiple series.

1. **For each route `r`**:
   - Compute baseline (median/P75) and scale (IQR/std)
   - Compute deviation for each observation

2. **Weight per route**:
   - Compute `w_r` based on traffic or importance

3. **Aggregate**:
   - Weighted sum or weighted average:
     \[
     \text{SystemDeviation}_t = \frac{\sum_r w_r \cdot \text{Deviation}_{r,t}}{\sum_r w_r}
     \]

4. **Optional smoothing** for visualization or alerting.

Output form:

- TIME
- VALUE
- WORKLOAD

Produce a minute-based time resolution
"""

"""
Resolutions:

1min
5min
10min
25min
50min
60min
1D
1W
"""

"""
OUR DATA HAS SOME ISSUES: IF A USER CANCELS A REQUEST (LET'S SAY IT'S TAKING TOO LONG)
WE DON'T CAPTURE THAT REQUEST - THE END PART OF IT.

We approximate system behavior using observable data.

GOALS:
- Estimate expected latency per route over time
- Normalize deviations across heterogeneous routes
- Aggregate into a system-wide metric weighted by workload

OUTPUT:
- TIME
- VALUE (system deviation)
- WORKLOAD

RESOLUTIONS:
1min, 5min, 10min, 25min, 50min, 60min, 1D, 1W
"""

import pandas as pd
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from typing import Dict

# =========================
# CONFIGURATION
# =========================

DATA_PATH = "log_nav_2026.csv"

RESOLUTION_MAP: Dict[str, str] = {
    "1min":  "1min",
    "5min":  "5min",
    "10min": "10min",
    "25min": "25min",
    "50min": "50min",
    "60min": "60min",
    "1day":  "1D",
    "1week": "1W"
}

# =========================
# MODEL CONFIG
# =========================

ALPHA = 0.1
MIN_HISTORY = 10
EPS = 1e-9

# =========================
# LOAD DATA
# =========================

df_raw = pd.read_csv(DATA_PATH)
df_raw = df_raw.rename(columns={"VALUE": "DURATION"})

df_raw['TIME'] = pd.to_datetime(
    df_raw['TIME'],
    format="%Y-%m-%dT%H:%M:%S",
    errors="coerce"
)

df_raw = df_raw.sort_values('TIME')
df_raw = df_raw.set_index('TIME')

# =========================
# BASE BUILDING (NO APPLY)
# =========================

def build_base_1min(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.reset_index()
    df['TIME'] = df['TIME'].dt.floor('min')

    # Global prior
    global_p75 = df['DURATION'].quantile(0.75)

    # Aggregate per route-minute
    agg = df.groupby(['ROUTE', 'TIME'], as_index=False)['DURATION'].quantile(0.75)
    agg = agg.rename(columns={'DURATION': 'OBSERVED'})

    workload = df.groupby(['ROUTE', 'TIME'], as_index=False)['DURATION'].count()
    workload = workload.rename(columns={'DURATION': 'WORKLOAD'})

    agg = agg.merge(workload, on=['ROUTE', 'TIME'])
    agg = agg.sort_values(['ROUTE', 'TIME'])

    # EWMA baseline (vectorized, safe)
    agg['HISTORICAL'] = (
        agg.groupby('ROUTE')['OBSERVED']
        .transform(lambda x: x.ewm(alpha=ALPHA, adjust=False).mean())
    )

    # shift → only past info
    agg['HISTORICAL'] = agg.groupby('ROUTE')['HISTORICAL'].shift(1)

    # cold start initialization
    agg['HISTORICAL'] = agg['HISTORICAL'].fillna(global_p75)

    # burn-in counter
    agg['COUNT'] = agg.groupby('ROUTE').cumcount()

    # normalized deviation
    agg['DEVIATION'] = (
        (agg['OBSERVED'] - agg['HISTORICAL']) /
        (agg['HISTORICAL'] + EPS)
    )

    # burn-in masking
    agg.loc[agg['COUNT'] < MIN_HISTORY, 'DEVIATION'] = None

    # sanity check
    assert 'ROUTE' in agg.columns
    assert 'TIME' in agg.columns

    return agg[['TIME', 'ROUTE', 'OBSERVED', 'HISTORICAL', 'DEVIATION', 'WORKLOAD']] \
        .sort_values(['TIME', 'ROUTE'])


# =========================
# RESOLUTION CONVERSION
# =========================

def convert_resolution(base: pd.DataFrame, resolution: str) -> pd.DataFrame:
    df = base.copy()
    df['TIME'] = df['TIME'].dt.floor(resolution)

    # weighted aggregation
    df['W_OBS'] = df['OBSERVED'] * df['WORKLOAD']
    df['W_HIST'] = df['HISTORICAL'] * df['WORKLOAD']

    agg = df.groupby(['ROUTE', 'TIME']).agg(
        OBSERVED=('W_OBS', 'sum'),
        HISTORICAL=('W_HIST', 'sum'),
        WORKLOAD=('WORKLOAD', 'sum'),
        DEVIATION=('DEVIATION', 'mean')
    ).reset_index()

    agg['OBSERVED'] = agg['OBSERVED'] / (agg['WORKLOAD'] + EPS)
    agg['HISTORICAL'] = agg['HISTORICAL'] / (agg['WORKLOAD'] + EPS)

    return agg.sort_values(['TIME', 'ROUTE'])


# =========================
# SYSTEM AGGREGATION
# =========================

def compute_system_stats(base: pd.DataFrame) -> pd.DataFrame:
    df = base.copy()

    # remove invalid rows
    df = df[df['DEVIATION'].notna()]

    if df.empty:
        return pd.DataFrame(columns=['TIME', 'VALUE', 'WORKLOAD'])

    df['WEIGHTED_DEV'] = df['DEVIATION'] * df['WORKLOAD']

    agg = df.groupby('TIME').agg(
        WEIGHTED_SUM=('WEIGHTED_DEV', 'sum'),
        TOTAL_WEIGHT=('WORKLOAD', 'sum')
    ).reset_index()

    agg['VALUE'] = agg['WEIGHTED_SUM'] / (agg['TOTAL_WEIGHT'] + EPS)

    result = agg[['TIME', 'VALUE']].copy()
    result['WORKLOAD'] = agg['TOTAL_WEIGHT']

    return result.sort_values('TIME')


# =========================
# SANITIZATION
# =========================

def sanitize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['TIME'] = df['TIME'].dt.strftime('%Y-%m-%dT%H:%M:%S')
    df = df.replace([float('inf'), float('-inf')], None)
    df = df.where(pd.notnull(df), None)
    return df


# =========================
# PRECOMPUTE BASE
# =========================

BASE_1MIN = build_base_1min(df_raw)

# =========================
# FASTAPI
# =========================

app = FastAPI(title="Latency System API")

@app.get("/")
def root():
    return FileResponse("viz.html")


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

    base_resampled = convert_resolution(BASE_1MIN, target_res)
    system_df = compute_system_stats(base_resampled)
    system_df = sanitize(system_df)

    return {
        "resolution": resolution,
        "count": len(system_df),
        "data": system_df.to_dict(orient="records")
    }


@app.get("/health")
def health():
    return {"status": "ok"}

