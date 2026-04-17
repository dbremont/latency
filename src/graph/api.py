# api.py
from fastapi import FastAPI, WebSocket, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Optional
import torch
import asyncio
from model import GNNSSM

app = FastAPI(title="QOIF-Latency Lab")

# Global model instance
model = GNNSSM()
model.eval()

class Task(BaseModel):
    type: int  # 0-9 task type ID
    size: float  # 0-1 normalized size
    arrival: float  # arrival time offset
    priority: Optional[int] = 1

class SimulationRequest(BaseModel):
    tasks: List[Task]

@app.post("/simulate")
async def simulate(request: SimulationRequest):
    """Run inference on task set."""
    # Convert to tensor format
    num_tasks = len(request.tasks)
    task_features = torch.tensor([[t.size, t.priority/10, 0.0] for t in request.tasks]).unsqueeze(0)
    task_types = torch.tensor([[t.type for t in request.tasks]]).unsqueeze(0)
    
    with torch.no_grad():
        latencies, state, graph = model(task_features, task_types, return_graph=True)
    
    latency_list = latencies.squeeze(0).tolist()
    total_latency = sum(latency_list)
    baseline = sum(t.size * 10 for t in request.tasks)  # Simple baseline: size * constant
    
    return {
        "latency": latency_list,
        "total_latency": total_latency,
        "deviation": total_latency - baseline,
        "graph": graph.squeeze(0).tolist(),  # NxN matrix
        "latent_state": state.squeeze(0).tolist()
    }

@app.websocket("/live")
async def live_inference(websocket: WebSocket):
    """WebSocket for real-time predictions during task streaming."""
    await websocket.accept()
    prev_state = None
    
    try:
        while True:
            data = await websocket.receive_json()
            tasks = data["tasks"]
            
            # Convert and predict
            task_features = torch.tensor([[t["size"], t["priority"]/10, 0.0] for t in tasks]).unsqueeze(0)
            task_types = torch.tensor([[t["type"] for t in tasks]]).unsqueeze(0)
            
            with torch.no_grad():
                latencies, prev_state = model(task_features, task_types, prev_state)
            
            await websocket.send_json({
                "latencies": latencies.squeeze(0).tolist(),
                "state": prev_state.squeeze(0).tolist()
            })
    except:
        await websocket.close()