# =========================
# MODEL CONFIG
# =========================

ALPHA = 0.1
MIN_HISTORY = 10
EPS = 1e-9

# =========================
# BASE BUILDING (NO APPLY)
# =========================

def build_base_1min(df: pd.DataFrame) -> pd.DataFrame:
    """
    Expected input:
        - TIME: Timestamp of the request
        - ROUTE: Route identifier
        - VALUE: Latency in ms

    Output:
        - TIME: Start of the minute window
        - ROUTE: Route
        - WORKLOAD: Number of requests
        - OBSERVED: {
            avg, p50, p95, max, var_log
          }
            - Var Log: Is the log of the variance of the latency - in our case used our average as a proxy for latency.
        - EXPECTED: p50 - computed from historical data using EWMA - if not enough history, use global average p50
        - DEVIATION: {
            avg:  Average of (VALUE - EXPECTED.p50) / VALUE,
            var_log: Average of log( (VALUE - EXPECTED.p50)^2 ) - used as a measure of variability in the deviation signal
        }
    """

    df = df.copy()
    df = df.reset_index(drop=True)
    df['TIME'] = df['TIME'].dt.floor('min')

    # -------- Aggregation --------
    agg = df.groupby(['ROUTE', 'TIME']).agg(
        avg=('VALUE', 'mean'),
        p50=('VALUE', 'median'),
        p95=('VALUE', lambda x: x.quantile(0.95)),
        max=('VALUE', 'max'),
        var_log=('VALUE', lambda x: np.log(x.var() + EPS) if len(x) > 1 else 0.0),
        WORKLOAD=('VALUE', 'count')
    ).reset_index()

    agg = agg.sort_values(['ROUTE', 'TIME'])

    # -------- Baseline (EWMA on p50) --------
    global_p50 = agg['p50'].mean()

    agg['expected_p50'] = (
        agg.groupby('ROUTE')['p50']
        .transform(lambda x: x.ewm(alpha=ALPHA, adjust=False).mean())
        .shift(1)
    ).fillna(global_p50)

    # -------- Deviation --------
    df = df.merge(
        agg[['ROUTE', 'TIME', 'expected_p50']],
        on=['ROUTE', 'TIME'],
        how='left'
    )

    df['dev'] = (df['VALUE'] - df['expected_p50']) / (df['VALUE'] + EPS)
    df['dev_var_log'] = np.log((df['VALUE'] - df['expected_p50'])**2 + EPS)

    dev_agg = df.groupby(['ROUTE', 'TIME']).agg(
        dev_avg=('dev', 'mean'),
        dev_var_log=('dev_var_log', 'mean')
    ).reset_index()

    agg = agg.merge(dev_agg, on=['ROUTE', 'TIME'], how='left')

    # Burn-in
    agg['history_count'] = agg.groupby('ROUTE').cumcount()
    agg.loc[agg['history_count'] < MIN_HISTORY, ['dev_avg', 'dev_var_log']] = np.nan

    # -------- Output formatting --------
    obs_cols = ['avg', 'p50', 'p95', 'max', 'var_log']
    agg['OBSERVED'] = agg[obs_cols].to_dict(orient='records')

    agg['EXPECTED'] = agg['expected_p50'].apply(lambda x: {'p50': x})

    agg['DEVIATION'] = agg[['dev_avg', 'dev_var_log']].rename(
        columns={'dev_avg': 'avg', 'dev_var_log': 'var_log'}
    ).to_dict(orient='records')

    return agg[['TIME', 'ROUTE', 'OBSERVED', 'EXPECTED', 'DEVIATION', 'WORKLOAD']] \
        .sort_values(['TIME', 'ROUTE'])

# =========================
# RESOLUTION CONVERSION
# =========================

def convert_resolution(base: pd.DataFrame, resolution: str) -> pd.DataFrame:
    """
    Input:
        - TIME: Start of the minute window
        - ROUTE: Route
        - WORKLOAD: Number of requests
        - OBSERVED: {
            avg, p50, p95, max, var_log
          }
            - Var Log: Is the log of the variance of the latency - in our case used our average as a proxy for latency.
        - EXPECTED: p50 - computed from historical data using EWMA - if not enough history, use global average p50
        - DEVIATION: {
            avg:  Average of (VALUE - EXPECTED.p50) / VALUE,
            var_log: Average of log( (VALUE - EXPECTED.p50)^2 ) - used as a measure of variability in the deviation signal
        }

    Output: Same format, but aggregated at the new resolution level.
    Note: The aggregation of the metrics should be done in a way that preserves the meaning as much as possible. 
    For example, avg can be aggregated as a weighted average, while var_log can be aggregated as a mean of the log variances.

    Aggregation strategy:
    - avg: Weighted average using WORKLOAD as weights (exact reconstruction of the global mean)
    - p50: Weighted average using WORKLOAD as weights (approximation; acceptable due to stability of the median under aggregation)
    - p95: Power-weighted average using WORKLOAD as weights:
        p95 = ( Σ w_i * p95_i^k / Σ w_i )^(1/k), with k ≈ 2–3
        (improves tail sensitivity vs linear averaging)
    - max: Max of the max values (exact)
    - var_log: Weighted mean of var_log using WORKLOAD as weights:
        var_log = Σ w_i * var_log_i / Σ w_i
        (more consistent with sample contribution than unweighted mean)
    """

    if base.empty:
        return base

    base = base.copy()

    # -------- Normalize observed --------
    obs_df = pd.json_normalize(base['OBSERVED'])
    df = pd.concat([base[['TIME', 'ROUTE', 'WORKLOAD']], obs_df], axis=1)

    df['TIME'] = df['TIME'].dt.floor(resolution)
    df = df[df['WORKLOAD'] > 0]

    # -------- Precompute weighted terms --------
    w = df['WORKLOAD']

    df['w_avg'] = df['avg'] * w
    df['w_p50'] = df['p50'] * w

    # Power-weighted p95 (k = 2.5)
    K = 2.5
    df['w_p95_pow'] = (df['p95'] ** K) * w

    # Weighted var_log
    df['w_var_log'] = df['var_log'] * w

    # -------- Aggregate --------
    agg = df.groupby(['ROUTE', 'TIME'], as_index=False).agg({
        'w_avg': 'sum',
        'w_p50': 'sum',
        'w_p95_pow': 'sum',
        'w_var_log': 'sum',
        'WORKLOAD': 'sum',
        'max': 'max'
    })

    W = agg['WORKLOAD']

    agg['avg'] = agg['w_avg'] / W
    agg['p50'] = agg['w_p50'] / W
    agg['p95'] = (agg['w_p95_pow'] / W) ** (1 / K)
    agg['var_log'] = agg['w_var_log'] / W

    # -------- Expected (EWMA) --------
    agg = agg.sort_values(['ROUTE', 'TIME'])

    global_p50 = agg['p50'].mean()

    agg['expected_p50'] = (
        agg.groupby('ROUTE')['p50']
        .transform(lambda x: x.ewm(alpha=ALPHA, adjust=False).mean().shift(1))
        .fillna(global_p50)
    )

    # -------- Deviation (spec-compliant) --------
    # avg deviation approximation:
    # E[(VALUE - expected)/VALUE] ≈ (avg - expected) / avg
    agg['dev_avg'] = (agg['avg'] - agg['expected_p50']) / (agg['avg'] + EPS)

    # var_log already approximates:
    # E[log((VALUE - expected)^2)] → we reuse aggregated var_log as proxy
    agg['dev_var_log'] = agg['var_log']

    # Apply minimum history constraint
    agg['history_count'] = agg.groupby('ROUTE').cumcount()
    mask = agg['history_count'] < MIN_HISTORY

    agg.loc[mask, ['dev_avg', 'dev_var_log']] = np.nan

    agg['DEVIATION'] = [
        {'avg': a, 'var_log': v}
        for a, v in zip(agg['dev_avg'], agg['dev_var_log'])
    ]

    # -------- Output --------
    obs_cols = ['avg', 'p50', 'p95', 'max', 'var_log']
    agg['OBSERVED'] = agg[obs_cols].to_dict(orient='records')

    agg['EXPECTED'] = agg['expected_p50'].apply(lambda x: {'p50': x})

    return (
        agg[['TIME', 'ROUTE', 'OBSERVED', 'EXPECTED', 'DEVIATION', 'WORKLOAD']]
        .sort_values(['TIME', 'ROUTE'])
    )

# =========================
# SYSTEM AGGREGATION
# =========================

def compute_system_stats(base: pd.DataFrame) -> pd.DataFrame:
    """
    Input (base format):
        - TIME: Timestamp of the window
        - ROUTE: Route
        - WORKLOAD: Number of requests
        - OBSERVED: {
            avg, p50, p95, max, var_log
            }
            - Var Log: Is the log of the variance of the latency - in our case used our average as a proxy for latency.
        - EXPECTED: p50 - computed from historical data using EWMA - if not enough history, use global average p50
        - DEVIATION: {
            avg:  Average of (VALUE - EXPECTED.p50) / VALUE,
            var_log: Average of log( (VALUE - EXPECTED.p50)^2 ) - used as a measure of variability in the deviation signal
        }
    
    Output:
        - TIME: Timestamp of the window
        - VALUE: System-wide deviation signal
        - WORKLOAD: Total workload across all routes

    Aggregation strategy:
    - For each time window and route compute:
    - TIME: Start of the window
    - VALUE = - VALUE: System-wide aggregated deviation, computed as the WORKLOAD-weighted expectation of route-level deviations.
    - WORKLOAD = Σ WORKLOAD 
    """

    df = base.copy()
    df = df[df['DEVIATION'].notna()]

    if df.empty:
        return pd.DataFrame(columns=['TIME', 'VALUE', 'WORKLOAD'])

    df['weighted_dev'] = df['DEVIATION'] * df['WORKLOAD']

    agg = df.groupby('TIME').agg(
        weighted_sum=('weighted_dev', 'sum'),
        total_weight=('WORKLOAD', 'sum')
    ).reset_index()

    agg['VALUE'] = agg['weighted_sum'] / (agg['total_weight'] + EPS)
    agg['WORKLOAD'] = agg['total_weight']

    return agg[['TIME', 'VALUE', 'WORKLOAD']].sort_values('TIME')


# =========================
# SANITIZATION
# =========================

def sanitize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['TIME'] = df['TIME'].dt.strftime('%Y-%m-%dT%H:%M:%S')
    df = df.replace([float('inf'), float('-inf')], None)
    df = df.where(pd.notnull(df), None)
    return df
