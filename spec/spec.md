# Latency Modelling Specification

We aim to construct a latency model from observational data stored in a CSV file with the following schema:

- **TIME** — timestamp of the request,
- **ROUTE** — endpoint or service identifier,
- **DURATION** — request latency (in milliseconds).

## Formulation

- Build some **metric** - that **capture** the latecy of the system - and routes over time, with the form:
  - **TIME** — aggregation timestamp (aligned to resolution)
  - **VALUE** — metric computation.
  - **WORKLOAD** — request volume (count) within the interval
- Support **explanation** (that connection of the latency data - or deriveed data) with the underlying system ontology.
- Support this time **resolutions**: 1min, 5min, 10min, 25min, 50min, 60min, 1day.
- ...

### System Model

> **Note**: The system state is fully determined by its history and the environment. For implementation purposes, one may introduce an explicit state space; however, for model specification this is not required.

> **Note:** A primary strategy for analyzing this system is **simulation**, via the generation of histories and their corresponding evolutions.

> We define the system as: $\mathcal{M} = (\mathcal{H}, \mathcal{Z}, \mathcal{E}, \mathcal{W}, T, C, P)$:

- $\mathcal{H}$: **History**  — sequences of past trajectories
- $\mathcal{Z}$: **Latent space** — (hidden internal factors: congestion, unserved work)
- $\mathcal{E}$: **Environment** — exogenous conditions
- $\mathcal{W}$: **Workload space** — (intensity, concurrency, pressure)
- $\mathbb{R}^+$: latency / cost domain

**History Process**:

> $H_t \in \mathcal{H}, \quad
H_t = {(S_\tau, Z_\tau, E_\tau, W_\tau) : \tau \le t}$

- $(H_t)$ is the **full system memory** (grows with time)

**State Construction**:

> $S_t = \phi(H_t)$:

- $\phi: \mathcal{H} \rightarrow \mathcal{S}$ is the **history projection operator**
- $S_t$ is a **lossy compression** of $H_t$ (not sufficient in general)

**Dynamics:**

$S_{t+1} = T(H_t, Z_t, E_t, W_t)$:

- $S_t \in \mathcal{S}$
- The state is a **sufficient statistic of all past evolution**

**Latent Process:**

$Z_t \sim P(,\cdot \mid S_t, W_t)$

- Encodes **unobserved internal structure**
- Evolves conditionally on system pressure and configuration

**Intrinsic Cost (Latency):**

$L_t = C(S_t, S_{t+1}, Z_t, E_t, W_t)$

- $L_t \in \mathbb{R}^+$
- Represents the **cost of transition under constraints**

### Metric Evaluation

- **Cold-Start Robustness** (Initialization Stability): The metric must produce valid and stable outputs when historical data is insufficient.
- **Sensitivity to spikes** – if a single request is extreme, it should reflect a high deviation.
- **Sensitivity to persistent drift** – if latency gradually increases, the metric should rise.
- **Robustness to noise** – normal small jitter shouldn’t trigger alerts.
- **Composability** – can be used in dashboards, smoothing, or downstream analytics.
- **Composability** (Algebraic & Pipeline Compatibility) The metric should support:
  - aggregation across routes (weighted or hierarchical),
  - resampling across time resolutions,
  - integration into downstream models (forecasting, anomaly detection).
- **Interpretability**: The metric must map cleanly to system behavior and support actionable reasoning:

  - clear baseline vs deviation semantics
  - monotonic relationship with “system health”
  - explainable in terms of queueing, saturation, or contention

## Data Quality Considerations

The dataset exhibits right-censoring bias:

- If a user cancels a request (e.g., due to excessive latency), the request is not fully observed.
- As a result, high-latency events are systematically underrepresented.
- The observed distribution is therefore truncated on the upper tail, leading to:
  - Underestimation of mean and variance
  - Distortion of tail quantiles (p95, p99)
  - Misleading conclusions about worst-case performance

This is not random missingness — it is informative censoring, since the probability of missing data increases with latency.

## Metric

> TO BE CONTINUE HERE -> ...

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


### Route Level

> ...

### System Level

> ...

### Critique
