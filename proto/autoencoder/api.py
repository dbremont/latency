# uvicorn api:app --reload --port 8000

# api.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import numpy as np
from collections import defaultdict
import torch
import torch.nn as nn
import torch.optim as optim

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Event(BaseModel):
    tau: int  # Task type
    t: float  # Start time
    d: float  # Observed duration (latency)

# ------------------------------------------------------------
# PyTorch Autoencoder Definition
# ------------------------------------------------------------
class Autoencoder(nn.Module):
    def __init__(self, input_dim, latent_dim=2):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.ReLU(),
            nn.Linear(8, latent_dim)   # bottleneck
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 8),
            nn.ReLU(),
            nn.Linear(8, 16),
            nn.ReLU(),
            nn.Linear(16, input_dim)
        )

    def forward(self, x):
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed, latent

    def encode(self, x):
        return self.encoder(x)

    def decode(self, z):
        return self.decoder(z)

@app.post("/analyze")
def analyze_qoif(stream: List[Event]):
    if len(stream) < 50:
        return {"error": "Not enough data"}

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
        baselines[tau] = np.percentile(durs, 20)

    # ---------------------------------------------------------
    # STEP 2: High-Performance State Extraction & History
    # ---------------------------------------------------------
    X, y = _extract_concurrent_states_fast(sorted_stream, n_tasks, baselines)
    if len(X) == 0:
        return {"error": "Extraction failed"}

    # ---------------------------------------------------------
    # STEP 3: Autoencoder for Latent Representation & Anomaly Detection
    # ---------------------------------------------------------
    input_dim = X.shape[1]
    latent_dim = 2

    # Convert to torch tensors
    X_tensor = torch.tensor(X, dtype=torch.float32)

    model = Autoencoder(input_dim, latent_dim)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.MSELoss()

    # Training loop
    model.train()
    for epoch in range(50):
        # Shuffle data manually (simple in-memory)
        perm = torch.randperm(X_tensor.size(0))
        X_shuffled = X_tensor[perm]
        for i in range(0, len(X_shuffled), 16):
            batch = X_shuffled[i:i+16]
            optimizer.zero_grad()
            reconstructed, _ = model(batch)
            loss = criterion(reconstructed, batch)
            loss.backward()
            optimizer.step()

    # Inference
    model.eval()
    with torch.no_grad():
        reconstructed_all, latent_all = model(X_tensor)
        # Reconstruction errors (MSE per sample)
        mse_per_sample = torch.mean((X_tensor - reconstructed_all) ** 2, dim=1)

    latent_coords = latent_all.numpy()
    reconstruction_errors = mse_per_sample.numpy()

    # ---------------------------------------------------------
    # STEP 4: Feature Importance (from first encoder layer weights)
    # ---------------------------------------------------------
    # First layer: model.encoder[0] is nn.Linear(input_dim, 16)
    first_linear = model.encoder[0]
    weights = first_linear.weight.detach().numpy()  # shape (16, input_dim)
    # Average absolute weight per input feature across the 16 neurons
    feature_importance = np.mean(np.abs(weights), axis=0).tolist()

    feature_names = [f"T{i}" for i in range(n_tasks)] + ["Total_Concurrency", "Recent_Burst"]

    # ---------------------------------------------------------
    # STEP 5: Prepare response
    # ---------------------------------------------------------
    return {
        "latent_coords": latent_coords.tolist(),
        "reconstruction_errors": reconstruction_errors.tolist(),
        "feature_importance": feature_importance,
        "feature_names": feature_names,
        "analyzed_data": [
            {"vec": x[:n_tasks].tolist(), "recon_error": round(float(err), 4)}
            for x, err in zip(X, reconstruction_errors)
        ]
    }


def _extract_concurrent_states_fast(stream, n_tasks, baselines):
    """
    O(N * avg_concurrency) algorithm.
    Captures concurrent vector, total concurrency, and recent burst history.
    """
    X = []
    y = []            # y kept for compatibility (delta_d), but autoencoder does not use it
    burst_window = 50.0
    N = len(stream)

    for i in range(N):
        curr = stream[i]
        t_start = curr['t']
        t_end = t_start + curr['d']

        # Deviation from baseline (only slowdowns)
        delta_d = curr['d'] - baselines.get(curr['tau'], 10)
        delta_d = max(0, delta_d)

        vec = [0] * n_tasks
        recent_burst = 0

        for j in range(N):
            if i == j:
                continue
            other = stream[j]

            if other['t'] >= t_end:
                break
            if other['t'] + other['d'] <= t_start:
                continue

            # Overlap
            vec[other['tau']] += 1

            # Burst within last 50 ms
            if 0 <= (t_start - other['t']) <= burst_window:
                recent_burst += 1

        feature_vec = vec + [sum(vec), recent_burst]
        X.append(feature_vec)
        y.append(delta_d)

    return np.array(X), np.array(y)