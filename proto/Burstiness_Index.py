import pandas as pd

"""
df structure
TIME: Arrival Time.
ROUTE: Task
VALUE: Latency

Shoudl the Burstiness Index be comptued in terms of a task type, or int erm of jus tttask arrival?

Compute the `Burstiness Index`.

Becuase our data has a temporal structure (work time day) - let try to fix it:

Time rescaling: Transform timestamps using the cumulative intensity $t' = \int_0^t \lambda(s),ds$ to remove time-varying rates before computing burstiness.
"""

df  =  pd.read_csv('../data/log_nav_2026.csv')

# Ensure TIME is datetime
df['TIME'] = pd.to_datetime(df['TIME'], format='mixed', errors='coerce')

df = df.dropna(subset=['TIME']).sort_values('TIME')

# =========================
# 3. FILTER: 8 AM – 4 PM
# =========================
df['hour'] = df['TIME'].dt.hour
df_work = df[(df['hour'] >= 8) & (df['hour'] < 16)].copy()

# =========================
# 4. INTRA-DAY INTERVALS
# =========================
df_work['date'] = df_work['TIME'].dt.date

tau_work = (
    df_work
    .groupby('date')['TIME']
    .diff() ## inter-arrival time.
    .dt.total_seconds()
    .dropna()
)

# Remove pathological values (optional but recommended)
tau_work = tau_work[tau_work > 0]
tau_work = tau_work[tau_work < 3600]  # remove large gaps (>1h)

# =========================
# 5. BURSTINESS INDEX (WORK HOURS)
# =========================
mu_work = tau_work.mean()
sigma_work = tau_work.std(ddof=1)

B_work = (sigma_work - mu_work) / (sigma_work + mu_work)

# =========================
# 6. OUTPUT
# =========================
print("=== Burstiness Analysis ===")
print(f"8am–4pm Burstiness Index: {B_work:.4f}")
