import numpy as np
import random
from dataclasses import dataclass
from typing import List, Tuple
import json

@dataclass
class ContentionEvent:
    timestamp: float
    task_type: int
    features: List[float]  # [size, priority, io_intensity]
    latency: float
    resource_state: List[float]  # [cpu_util, mem_util, io_wait]

class SyntheticContentionGenerator:
    """
    Simulates resource contention dynamics using a queuing model.
    
    This is the "physics engine" for generating training data when
    no real traces are available.
    """
    
    def __init__(self, num_task_types=10, num_resources=3):
        self.num_task_types = num_task_types
        self.num_resources = num_resources
        
        # Contention matrix: how much task type j interferes with i
        self.contention_matrix = np.random.beta(0.5, 2, (num_task_types, num_task_types))
        np.fill_diagonal(self.contention_matrix, 0)  # No self-interference
        
        # Base latency per task type (no contention)
        self.base_latency = np.random.exponential(10, num_task_types)
        
        # Resource capacity
        self.resource_capacity = np.ones(num_resources)
        
    def generate_trace(self, duration: float, arrival_rate: float, 
                       seed: int = None) -> List[ContentionEvent]:
        """Generate a synthetic contention trace."""
        if seed:
            np.random.seed(seed)
            random.seed(seed)
            
        events = []
        current_time = 0
        resource_load = np.zeros(self.num_resources)
        active_tasks = []  # (task_type, size, remaining_time, resources_needed)
        
        while current_time < duration:
            # Poisson arrival
            interarrival = np.random.exponential(1.0 / arrival_rate)
            current_time += interarrival
            
            if current_time > duration:
                break
                
            # Generate new task
            task_type = random.randint(0, self.num_task_types - 1)
            size = np.random.exponential(0.5)  # normalized size
            priority = np.random.uniform(0.5, 1.5)
            io_intensity = np.random.beta(1, 3)
            
            features = [size, priority, io_intensity]
            
            # Resources needed by this task (based on type)
            resources_needed = self._sample_resources(task_type, size)
            
            # Compute contention from currently active tasks
            contention_factor = self._compute_contention(task_type, active_tasks)
            
            # Resource saturation effect
            resource_saturation = np.sum(np.maximum(0, resource_load + resources_needed - self.resource_capacity))
            
            # Final latency = base * size * (1 + contention + saturation)
            latency = (self.base_latency[task_type] * size * 
                      (1 + contention_factor) * 
                      (1 + resource_saturation))
            
            # Update resource load
            resource_load += resources_needed
            active_tasks.append({
                'type': task_type,
                'remaining': latency,
                'resources': resources_needed
            })
            
            # Record event
            events.append(ContentionEvent(
                timestamp=current_time,
                task_type=task_type,
                features=features,
                latency=latency,
                resource_state=resource_load.copy()
            ))
            
            # Remove completed tasks
            active_tasks = [t for t in active_tasks if t['remaining'] > 0]
            for t in active_tasks:
                t['remaining'] -= 1.0  # Simplified: decrement by 1 time unit
            
            # Decay resource load based on completions
            resource_load = self._compute_current_load(active_tasks)
            
        return events
    
    def _sample_resources(self, task_type: int, size: float) -> np.ndarray:
        """Sample resource requirements for a task."""
        # CPU-bound: high CPU, low mem/IO
        if task_type < 3:
            return np.array([size * random.uniform(0.5, 1.0), 
                            size * random.uniform(0.0, 0.3),
                            size * random.uniform(0.0, 0.2)])
        # Memory-bound
        elif task_type < 6:
            return np.array([size * random.uniform(0.1, 0.4),
                            size * random.uniform(0.6, 1.0),
                            size * random.uniform(0.0, 0.3)])
        # IO-bound
        else:
            return np.array([size * random.uniform(0.0, 0.2),
                            size * random.uniform(0.0, 0.3),
                            size * random.uniform(0.5, 1.0)])
    
    def _compute_contention(self, task_type: int, active_tasks: List) -> float:
        """Compute contention factor from active tasks."""
        if not active_tasks:
            return 0.0
        
        contention = 0.0
        for task in active_tasks:
            contention += self.contention_matrix[task_type, task['type']]
        
        return min(contention / len(active_tasks), 2.0)  # Cap at 2x
    
    def _compute_current_load(self, active_tasks: List) -> np.ndarray:
        """Compute current resource load from active tasks."""
        load = np.zeros(self.num_resources)
        for task in active_tasks:
            load += task['resources'] * 0.1  # Decay factor
        return load

# Usage: Generate 1 hour of synthetic contention data
generator = SyntheticContentionGenerator()
trace = generator.generate_trace(duration=3600, arrival_rate=10.0, seed=42)
print(f"Generated {len(trace)} events")