# Modelling

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
