# uvicorn api:app --reload --port 8000

# api.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import xgboost as xgb
import umap
import numpy as np
from collections import defaultdict

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Event(BaseModel):
    tau: int  # Task type
    t: float  # Start time
    d: float  # Observed duration (latency)

@app.post("/analyze")
def analyze_qoif(stream: List[Event]):
    if len(stream) < 50: return {"error": "Not enough data"}

    sorted_stream = sorted([e.dict() for e in stream], key=lambda x: x['t'])
    n_tasks = max(e['tau'] for e in sorted_stream) + 1
    
    # ---------------------------------------------------------
    # STEP 1: Robust Context-Dependent Baselines (d_0)
    # ---------------------------------------------------------
    baselines = {}
    durations_by_tau = defaultdict(list)
    for e in sorted_stream:
        durations_by_tau[e['tau']].append(e['d'])
        
    for tau, durs in durations_by_tau.items():
        # Use 20th percentile as baseline. More robust to outliers than mean.
        baselines[tau] = np.percentile(durs, 20)

    # ---------------------------------------------------------
    # STEP 2: High-Performance State Extraction & History
    # ---------------------------------------------------------
    X, y = _extract_concurrent_states_fast(sorted_stream, n_tasks, baselines)
    
    if len(X) == 0: return {"error": "Extraction failed"}

    # ---------------------------------------------------------
    # STEP 3: Discovery Engine (XGBoost)
    # ---------------------------------------------------------
    model = xgb.XGBRegressor(n_estimators=60, max_depth=4, learning_rate=0.1)
    model.fit(X, y)

    # ---------------------------------------------------------
    # STEP 4: Topology (Tree Embeddings -> UMAP)
    # ---------------------------------------------------------
    # XGBOOST 2.0+ FIX: Must use underlying Booster and DMatrix for pred_leaf
    dmatrix = xgb.DMatrix(X)
    leaf_embeddings = model.get_booster().predict(dmatrix, pred_leaf=True)
    
    reducer = umap.UMAP(n_neighbors=15, min_dist=0.1, metric='hamming')
    umap_coords = reducer.fit_transform(leaf_embeddings)

    # ---------------------------------------------------------
    # STEP 5: Extraction & Intervention Rules
    # ---------------------------------------------------------
    # Pass feature names so the extracted rules are human-readable
    feature_names = [f"T{i}" for i in range(n_tasks)] + ["Total_Concurrency", "Recent_Burst"]
    
    # XGBOOST 2.0+ FIX: Get dump from underlying booster
    dump = model.get_booster().get_dump(dump_format='text')
    rules = extract_top_rules(dump, feature_names, threshold=15.0)
    importance = model.feature_importances_.tolist()

    return {
        "umap_coords": umap_coords.tolist(),
        "rules": rules,
        "importance": importance,
        "feature_names": feature_names,
        "analyzed_data": [{"vec": x[:n_tasks].tolist(), "ld": round(float(y_val), 1)} for x, y_val in zip(X, y)]
    }


def _extract_concurrent_states_fast(stream, n_tasks, baselines):
    """
    O(N * avg_concurrency) algorithm instead of O(N^2).
    Captures concurrent vector, total concurrency, and recent burst history.
    """
    X = []
    y = []
    burst_window = 50.0 # History window in ms (captures H_<t)
    N = len(stream)
    
    for i in range(N):
        curr = stream[i]
        t_start = curr['t']
        t_end = t_start + curr['d']
        
        # Calculate deviation from context-dependent baseline
        delta_d = curr['d'] - baselines.get(curr['tau'], 10)
        delta_d = max(0, delta_d) # We only model slowdowns (contention), not speedups
        
        vec = [0] * n_tasks
        recent_burst = 0
        
        # Sliding window: only check tasks that could possibly overlap
        for j in range(N):
            if i == j: continue
            other = stream[j]

            # Optimization 1: If the other task started AFTER current ended, stop looking forward
            if other['t'] >= t_end: break 
            
            # Optimization 2: If the other task ended BEFORE current started, skip
            if other['t'] + other['d'] <= t_start: continue
            
            # They overlap! Add to concurrent state vector
            vec[other['tau']] += 1
            
            # Check history (burstiness in the window prior to this task starting)
            if 0 <= (t_start - other['t']) <= burst_window:
                recent_burst += 1

        # Final Feature Vector: [T0...Tk, Total_Concurrency, Recent_Burst]
        feature_vec = vec + [sum(vec), recent_burst]
        
        X.append(feature_vec)
        y.append(delta_d)
        
    return np.array(X), np.array(y)


def extract_top_rules(dump, feature_names, threshold=15.0):
    """Parse XGBoost trees into readable N-way interaction rules."""
    top_rules = []
    
    for tree_str in dump:
        nodes = {}
        for line in tree_str.split('\n'):
            line = line.strip()
            if not line: continue
            if 'leaf=' in line:
                nid = int(line.split(':')[0])
                val = float(line.split('leaf=')[1])
                nodes[nid] = {'type': 'leaf', 'value': val}
            else:
                nid = int(line.split(':')[0])
                # Extract condition e.g., "f2<2"
                cond_raw = line.split(']')[0].split('[')[1] 
                f_idx = int(cond_raw.split('<')[0].replace('f', ''))
                threshold_val = cond_raw.split('<')[1]
                
                # Map back to human readable name
                fname = feature_names[f_idx] if f_idx < len(feature_names) else f"f{f_idx}"
                cond_clean = f"{fname} < {threshold_val}"
                
                yes = int(line.split('yes=')[1].split(',')[0])
                no = int(line.split('no=')[1].split(',')[0])
                nodes[nid] = {'type': 'split', 'cond': cond_clean, 'yes': yes, 'no': no}

        def trace_path(nid, current_path):
            node = nodes[nid]
            if node['type'] == 'leaf':
                if node['value'] > threshold: 
                    top_rules.append({"path": " AND ".join(current_path), "impact": round(node['value'], 1)})
                return
            trace_path(node['yes'], current_path + [node['cond']])
            trace_path(node['no'], current_path + [f"NOT({node['cond']})"])

        trace_path(0, [])

    unique_rules = list({r['path']: r for r in top_rules}.values())
    unique_rules.sort(key=lambda x: x['impact'], reverse=True)
    return unique_rules[:5]