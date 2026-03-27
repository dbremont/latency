import pandas as pd
import numpy as np
import time
from typing import List, Dict

# -----------------------------
# Load time series
# -----------------------------
df = pd.read_csv("data/latency.csv", parse_dates=["Time"])
times = pd.to_datetime(df["Time"])
values = df["Value"].values
print(f"Loaded {len(values)} data points.")

# -----------------------------
# Statistics functions
# -----------------------------
def compute_statistics(data: np.ndarray) -> Dict[str, float]:
    """Compute core metrics for a 1D array."""
    if len(data) == 0:
        return {metric: np.nan for metric in ["avg", "p50", "p75", "var_log", "max", "p95"]}
    return {
        "avg": np.mean(data),
        "p50": np.median(data),
        "p75": np.percentile(data, 75),
        "var_log": np.var(np.log1p(data)),
        "max": np.max(data),
        "p95": np.percentile(data, 95)
    }

# -----------------------------
# Compute 1-min resolution
# -----------------------------
def compute_1min_stats(values: np.ndarray, times: pd.Series) -> pd.DataFrame:
    """Compute statistics at 1-minute windows directly from raw data."""
    df_temp = pd.DataFrame({"Time": times, "Value": values}).set_index("Time")
    stats = []
    for ts, group in df_temp.resample("1min"):
        s = compute_statistics(group["Value"].values)
        s["timestamp"] = ts
        stats.append(s)
    return pd.DataFrame(stats)

# -----------------------------
# Derive higher resolutions
# -----------------------------
def derive_higher_res(stats_1min: pd.DataFrame, resolutions: List[str]) -> Dict[str, pd.DataFrame]:
    """
    Compute higher resolution statistics derived from the 1-min base stats.
    `resolutions` should include '1min' as first element.
    """
    stats_1min = stats_1min.set_index("timestamp")
    multi_res_stats = {"1min": stats_1min.reset_index()}

    for res in resolutions[1:]:
        # Aggregate each metric from 1-min base
        df_res = stats_1min.resample(res).agg({
            "avg": "mean",
            "p50": "median",
            "p75": "median",
            "var_log": "mean",
            "max": "max",
            "p95": "median"
        }).reset_index()
        multi_res_stats[res] = df_res

    return multi_res_stats

# -----------------------------
# Compute consistency errors
# -----------------------------
def compute_consistency_errors(values: np.ndarray, times: pd.Series, resolutions: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Compute the error between:
    - metrics computed directly from raw data at each resolution
    - metrics derived from 1-min statistics
    """
    # 1-min base
    stats_1min = compute_1min_stats(values, times)

    # Derived multi-resolution
    derived_stats = derive_higher_res(stats_1min, resolutions)

    errors = {}
    df_temp = pd.DataFrame({"Time": times, "Value": values}).set_index("Time")

    for res in resolutions:
        # Direct stats from raw data at this resolution
        direct_stats = []
        for ts, group in df_temp.resample(res):
            s = compute_statistics(group["Value"].values)
            direct_stats.append(s)
        direct_stats_df = pd.DataFrame(direct_stats)

        # Stats derived from 1-min base
        derived_df = derived_stats[res].drop(columns=["timestamp"])

        # Relative errors
        diff = (direct_stats_df - derived_df).abs() / (direct_stats_df + 1e-9)
        errors[res] = diff.mean().to_dict()

    return errors

# -----------------------------
# Benchmark setup
# -----------------------------
resolutions = ["1min", "5min", "10min", "25min", "50min", "1h", "1d"]  # lowercase for pandas

# -----------------------------
# Run benchmark
# -----------------------------
start_time = time.time()
consistency_errors = compute_consistency_errors(values, times, resolutions)
elapsed_time = time.time() - start_time

# -----------------------------
# Display results
# -----------------------------
print(f"Consistency Errors per resolution (derived from 1-min base):")
for res, errs in consistency_errors.items():
    print(f"  {res}: { {k: round(v*100,4) for k,v in errs.items()} }")
print(f"Elapsed time: {elapsed_time:.2f}s")