# model.py
import torch
import torch.nn as nn
import torch.nn.functional as F

class GNNSSM(nn.Module):
    """
    Graph Neural Network + State Space Model for contention dynamics.
    
    - Nodes: tasks
    - Edges: learned contention weights A_{ij}
    - State: latent resource vector S_t
    """
    def __init__(self, task_feature_dim=3, hidden_dim=64, state_dim=32, num_layers=2):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.state_dim = state_dim
        
        # Task encoder
        self.task_encoder = nn.Sequential(
            nn.Linear(task_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim)
        )
        
        # Learnable contention graph (edges between task types)
        # In production, this would be dynamically computed per batch
        self.contention_weights = nn.Parameter(torch.randn(10, 10) * 0.1)  # 10 task types
        
        # GNN layers (using simple message passing)
        self.gnn_layers = nn.ModuleList([
            nn.Linear(hidden_dim, hidden_dim) for _ in range(num_layers)
        ])
        
        # State transition (latent resource dynamics)
        self.state_transition = nn.GRUCell(hidden_dim, state_dim)
        
        # Latency predictor
        self.latency_head = nn.Sequential(
            nn.Linear(hidden_dim + state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )
        
    def compute_interaction_graph(self, task_types, features):
        """Compute contention edges based on task types and features."""
        # A_ij = softmax(contention_weights[type_i, type_j] * similarity(f_i, f_j))
        batch_size, num_tasks = task_types.shape
        
        # Get contention base from task types
        type_pairs = task_types.unsqueeze(-1)  # (B, N, 1)
        base_weights = self.contention_weights[type_pairs, type_pairs.transpose(-2, -1)]
        
        # Scale by feature similarity
        feat_norm = F.normalize(features, dim=-1)
        similarity = torch.bmm(feat_norm, feat_norm.transpose(-2, -1))
        
        adjacency = torch.sigmoid(base_weights) * similarity
        return adjacency
    
    def forward(self, task_features, task_types, prev_state=None, return_graph=False):
        """
        Args:
            task_features: (B, N, D_feat)
            task_types: (B, N) integer task type IDs
            prev_state: (B, state_dim) or None
        Returns:
            latencies: (B, N)
            new_state: (B, state_dim)
            graph: (B, N, N) adjacency matrix (if return_graph)
        """
        batch_size, num_tasks, _ = task_features.shape
        
        # Encode tasks
        task_embeddings = self.task_encoder(task_features)  # (B, N, hidden_dim)
        
        # Build contention graph
        adjacency = self.compute_interaction_graph(task_types, task_embeddings)
        
        # GNN message passing
        h = task_embeddings
        for layer in self.gnn_layers:
            # Aggregate neighbors
            neighbor_agg = torch.bmm(adjacency, h)  # (B, N, hidden_dim)
            h = layer(h + neighbor_agg)
            h = F.relu(h)
        
        # Aggregate task embeddings to global state
        global_context = h.mean(dim=1)  # (B, hidden_dim)
        
        # Update latent resource state
        if prev_state is None:
            prev_state = torch.zeros(batch_size, self.state_dim, device=h.device)
        new_state = self.state_transition(global_context, prev_state)
        
        # Predict per-task latency
        combined = torch.cat([h, new_state.unsqueeze(1).expand(-1, num_tasks, -1)], dim=-1)
        latencies = self.latency_head(combined).squeeze(-1)  # (B, N)
        
        if return_graph:
            return latencies, new_state, adjacency
        return latencies, new_state