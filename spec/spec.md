# Latency Modelling Specification

> This document defines a comprehensive framework for modeling, analyzing, and representing system latency. The goal is to construct a **data-driven, explainable, and multi-resolution latency model** that captures the behavior of requests across system routes, workloads, and resources.

Open Questions:

- For efficiency, we rely on 1‑minute metrics to avoid recomputing over many GBs of data. How can we maintain consistency when supporting multi-resolution aggregation? Specifically, how can we ensure that, for example, the P95 latency over one hour matches the P95 derived from the aggregation of 1‑minute buckets?
  - t-digest,
  - **HDR** Histogram.
- How can we reason about the identifiability of the latent resource–route matrix?

## Formulation

We aim to construct a latency model from observational data stored in a CSV file with the following schema:

- **TIME** — timestamp of the request,
- **ROUTE** — endpoint or service identifier,
- **DURATION** — request latency (in milliseconds).

Build some **metric** - that **capture** the latecy of the system - and routes over time, with the form:

- Data Format
  - **TIME** — aggregation timestamp (aligned to resolution)
  - **VALUE** — metric computation.
  - **WORKLOAD** — request volume (count) within the interval
- Support **explanation** (that connection of the latency data - or deriveed data) with the underlying system ontology.
- Support this time **resolutions**: 1min, 5min, 10min, 25min, 50min, 60min, 1day.
- ...

### Data Quality Considerations

The dataset exhibits right-censoring bias:

- If a user cancels a request (e.g., due to excessive latency), the request is not fully observed.
- As a result, high-latency events are systematically underrepresented.
- The observed distribution is therefore truncated on the upper tail, leading to:
  - Underestimation of mean and variance
  - Distortion of tail quantiles (p95, p99)
  - Misleading conclusions about worst-case performance

This is not random missingness — it is informative censoring, since the probability of missing data increases with latency.

## Response Schema

### Route Data

- TIME: Timestamp of the window (e.g., 1min, 5min, 10min, etc.)
- ROUTE: Route of the request.
- WORKLOAD: Total workload for the time window
- OBSERVED: Dictionary with computed statistics (avg, p50, p75, var_log, max, p95)
- EXPECTED: Dictionary with computed historical statistics (p50, p75, var_log)
- DEVIATION: Normalized  OBSERVED - avg - EXPECTED.p50), the log variance of this.

### System Wide Data

- TIME: Timestamp of the window (e.g., 1min, 5min, 10min, etc.)
- VALUE: System-wide aggregated deviation, computed as the WORKLOAD-weighted expectation of route-level deviations.
- WORKLOAD: Total workload for the time window

## Expected-Reference Data Computation

- ...

## System Model

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

## Time Resolution Recasting

> How to derived  Average, P50 Average (Median), P75 Average, Variance of Log-Latency, Max Value - using 1min  - data (statistics) resolution?

> How to **check the correcteness** of the derivered **metrics**?

> How can we ensure that, for example, the P95 latency over one hour matches the P95 derived from the aggregation of 1‑minute buckets?

### Evaluation Criteria

- Compression ratio: the size of the compressed representation compared to the original data.
- Consistency: It's the P95 latency from the orignial data - equal to the P95 latency from the reconstructed data.
- Computational efficiency: the time it takes to compress and decompress the data, as well as the time it takes to compute statistics

### Strategy

> Followingg several benchmarks in `proto/tsc` we have choosen ...

## Representation View

> How to **provide a set of analytical views** over the system’s state and dynamics that support latency characterization and diagnostic analysis?

Categories:

- State & Dynamics Views (Phase Space, Elasticity, Bifurcation)
- Latent & Causal Views (Congestion Inference, Causal Topology)
- Observability & Statistical Views (Quantile Surfaces, Distributions, Variance)
- Boundary & Informational Views (Survival/Hazard, Memory Decay)

### Time Resolution Route Level Latency Representation

> Which are the metrics that can capture a task latency?

#### Criteria

| **Criterion**            | **Definition**                                                                                                                                                                          |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Robustness               | Ability of a metric to consistently represent system behavior under variable conditions, including extreme events and fluctuations. Tail sensitivity and persistence detection are key. |
| Interpretability         | Ease of understanding the metric for operations, diagnostics, and decision-making.                                                                                                      |
| Computational Efficiency | Suitability for high-frequency, multi-route measurements without excessive resource consumption.                                                                                        |
| Sensitivity              | Ability to capture small but meaningful changes in latency dynamics, detecting deviations from baseline.                                                                                |


#### Metrics

| **Metric**                              | **Description**                                                                             | **Evaluation**                                                                                                                            |
| --------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Average                                 | Arithmetic mean of all latency measurements in the interval.                                | Robustness: Low (sensitive to outliers) <br> Interpretability: High <br> Computational Efficiency: High <br> Sensitivity: Medium          |
| P50 Average (Median)                    | 50th percentile latency, central value of the distribution.                                 | Robustness: Medium (resistant to outliers) <br> Interpretability: High <br> Computational Efficiency: High <br> Sensitivity: Medium       |
| P95 Average                             | 95th percentile latency, captures moderate tail behavior.                                   | Robustness: Medium-High (captures moderate tail) <br> Interpretability: High <br> Computational Efficiency: High <br> Sensitivity: Medium |
| Spread Measure: Variance of Log-Latency | Measures variability in log-transformed latencies, highlighting multiplicative differences. | Robustness: High (captures tail spread) <br> Interpretability: Medium <br> Computational Efficiency: Medium <br> Sensitivity: High        |
| Max Value                               | Maximum observed latency in the interval.                                                   | Ro                                                                                                                                        |

### Time Resolution System Level Latency Representation

> ...

### Time Resolution Route Level Latency Rate of Change Representation

> ...

### Time Resolution System Level Latency Rate of Change Representation

> ...

### Time Resolution Route Level Latency Deviation Representation

> ...

### Time Resolution System Level Latency Deviation Representation

> ...

### Time Resolution Variance Latency Representation

> ..

### System Latency Distribution Representation

> ...

### Route Latency Distributon Representation

> ...

### System Quantile Surface Representation

> ...

### Route Quantile Surface Representation

> ...

### System Workload Based Latency Representation

> $L = f(W)$

### System Elasticity Representation

> $\frac{dL}{dW}$

> How to characterize and represent the system’s ability to absorb, adapt to, and recover from variations in workload and operating conditions without degradation of performance?

### System Workload Latency Decomposition Representation

> ...

### (Intra) System Latency Deviation Decomposition Representation

> How can we explain **System Latency Deviation** at different levels: inter-workload (history), intra-workload, and hidden variables? Specifically, how can we decompose the intra-workload latency deviation contributions down to the lowest level of task computation within a workload?

> In this section, we focus on: **decomposing the intra-workload latency deviation contributions**.

> See other strategies in [A Guide to Times Series Regime Change - System Latency Deviation Decomposition Representation](https://www.notion.so/A-Guide-to-Times-Series-Regime-Change-32ec0f5171ec806d991fdc62b49f9813?source=copy_link).

#### Problem Definition

- The goal i sto produce a a repersntaion that can aid simulation of workload latency.
- For a task set of size $n$, there are $2^n$ possible subsets (workload), assuming the order of tasks does not matter.
- The goal is to quantify how each task within a workload contributes to the observed latency deviation.
- The goal is to be aware of the interaction (interference) - between the routes - and how this impacts latency deviation - for a latter analysis -  of the routes - and resources used by them.

#### Strategy

> We aim to learn a **latent resource–route interaction model** that characterizes how each task engages system resources across all workloads, and how these interactions contribute to **intra-workload latency deviations**.

> This approach follows a common modeling pattern observed in **Latent Dirichlet Allocation (LDA), Structural Equation Models (SEM), low-rank interaction models, latent factor models**, and related frameworks.

> The resulting **latent interaction matrix** can be leveraged for **diagnostic analysis, workload optimization,** and **predictive modeling of system latency** under new workload combinations.

#### Latent Share Resource Utilization Matrix

> **Note:** The resources are abstract, latent, and synthetic, learned from the model. The **resulting matrix** captures how each route contributes to **latent resources**. It can later be used to **analyze and explain the contribution of interference** between tasks within a workload to the observed latency deviation.

> Each entry $p_{t,r}$ represents the **pressure or utilization of latent resource $r$ by task $t$**.

| **Route (Task)** | **Latent Resource 1** | **Latent Resource 2** | **Latent Resource 3** | **Latent Resource 4** | … |
| ---------------- | -------------- | -------------- | -------------- | -------------- | - |
| **Route 1**      | $p_{1,1}$      | $p_{2,1}$      | $p_{3,1}$      | $p_{4,1}$      | … |
| **Route 2**      | $p_{1,2}$      | $p_{2,2}$      | $p_{3,2}$      | $p_{4,2}$      | … |
| **Route 3**      | $p_{1,3}$      | $p_{2,3}$      | $p_{3,3}$      | $p_{4,3}$      | … |
| **…**            | …              | …              | …              | …              | … |

#### Implementation

> ...

### History Latency Dependency Representation

> How current latency depends on pass latencies?

### Censored Latency Representation

> ....

### System Bifurcation Representation

> ...

### Latent State (Congestion) Inference Representation

You defined Zt​∼P(⋅∣St​,Wt​) as unobserved internal structure. You need a view that represents the inferred hidden state—such as estimated shadow queue depth or lock contention—using techniques like Hidden Markov Models or Kalman filtering on the observed Lt​.

### Critique

> ...

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

## Validation

> How to validate the the resulting representations?
