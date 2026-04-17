# train_on_sample.py
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from sklearn.preprocessing import LabelEncoder, StandardScaler
import warnings
warnings.filterwarnings('ignore')

# ============================================
# 1. LOAD AND PARSE YOUR DATA
# ============================================

def load_sample_data(filepath='sample.csv'):
    """Load and parse the sample.csv with your exact format."""
    df = pd.read_csv(filepath)
    
    # Parse timestamp
    df['timestamp'] = pd.to_datetime(df['TIME'], errors='coerce')
    
    # Extract task type (clean the string)
    df['task_type_raw'] = df['TASK_TYPE'].str.strip()
    
    # Create numeric task type ID
    le = LabelEncoder()
    df['task_type_id'] = le.fit_transform(df['task_type_raw'])
    
    # Value is the latency/execution time
    df['latency_ms'] = df['VALUE']
    
    # Sort by time
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    # Create time deltas (seconds since start)
    df['time_sec'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds()
    
    print(f"Loaded {len(df)} events")
    print(f"Unique task types: {dict(zip(le.classes_, range(len(le.classes_))))}")
    print(f"Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    return df, le

df, label_encoder = load_sample_data('sample.csv')
print("\nFirst 5 rows:")
print(df[['time_sec', 'task_type_raw', 'latency_ms']].head())

# ============================================
# 2. FEATURE ENGINEERING FOR CONTENTION
# ============================================

class ContentionFeatureBuilder:
    """Build features that capture resource contention dynamics."""
    
    def __init__(self, window_size_sec=60):
        self.window_size_sec = window_size_sec
        
    def build_features(self, df):
        """Create features for each task based on recent history."""
        
        # Basic features
        features = []
        labels = []
        
        for idx in range(len(df)):
            current_time = df.iloc[idx]['time_sec']
            current_task = df.iloc[idx]['task_type_id']
            current_latency = df.iloc[idx]['latency_ms']
            
            # Look at tasks in the last N seconds (contention window)
            window_mask = (df['time_sec'] >= current_time - self.window_size_sec) & \
                         (df['time_sec'] < current_time)
            recent_tasks = df[window_mask]
            
            # Feature 1: Recent task density (how many tasks in window)
            task_density = len(recent_tasks) / self.window_size_sec
            
            # Feature 2: Recent latency average
            recent_latency_mean = recent_tasks['latency_ms'].mean() if len(recent_tasks) > 0 else 0
            
            # Feature 3: Task type diversity (entropy of recent types)
            if len(recent_tasks) > 0:
                type_counts = recent_tasks['task_type_id'].value_counts(normalize=True)
                diversity = -sum(p * np.log(p + 1e-10) for p in type_counts)
            else:
                diversity = 0
            
            # Feature 4: Current task encoding (one-hot of type)
            task_onehot = np.zeros(len(label_encoder.classes_))
            task_onehot[current_task] = 1
            
            # Feature 5: Time since last same-type task
            same_type_mask = df['task_type_id'] == current_task
            prev_same = df[same_type_mask & (df['time_sec'] < current_time)]
            time_since_same = current_time - prev_same['time_sec'].iloc[-1] if len(prev_same) > 0 else 60
            
            # Combine features
            feat_vec = np.concatenate([
                [task_density],
                [recent_latency_mean / 1000],  # normalize
                [diversity],
                [min(time_since_same / 60, 1.0)],  # normalize to 0-1
                task_onehot
            ])
            
            features.append(feat_vec)
            labels.append(current_latency)
        
        return np.array(features), np.array(labels)

# Build features
builder = ContentionFeatureBuilder(window_size_sec=30)
X, y = builder.build_features(df)
print(f"\nFeature shape: {X.shape}")
print(f"Labels shape: {y.shape}")

# Train/val split (chronological - important for time series)
split_idx = int(len(X) * 0.7)
X_train, X_val = X[:split_idx], X[split_idx:]
y_train, y_val = y[:split_idx], y[split_idx:]

# Normalize features
scaler = StandardScaler()
X_train = scaler.fit_transform(X_train)
X_val = scaler.transform(X_val)

print(f"Training samples: {len(X_train)}, Validation: {len(X_val)}")

# ============================================
# 3. PYTORCH MODEL FOR CONTENTION PREDICTION
# ============================================

class ContentionPredictor(nn.Module):
    """
    Neural network that learns:
    - How task types interfere with each other
    - How recent load affects current latency
    """
    
    def __init__(self, input_dim, hidden_dims=[64, 32], num_task_types=None):
        super().__init__()
        
        self.num_task_types = num_task_types or input_dim - 4  # task one-hot is last N dims
        
        # Learnable contention matrix between task types
        self.contention_matrix = nn.Parameter(torch.randn(self.num_task_types, self.num_task_types) * 0.1)
        
        # Feature processing layers
        layers = []
        prev_dim = input_dim
        for h_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, h_dim),
                nn.ReLU(),
                nn.Dropout(0.2)
            ])
            prev_dim = h_dim
        
        layers.append(nn.Linear(prev_dim, 1))
        layers.append(nn.ReLU())  # Latency should be positive
        
        self.mlp = nn.Sequential(*layers)
        
        # Contention attention mechanism
        self.contention_attention = nn.MultiheadAttention(
            embed_dim=self.num_task_types, 
            num_heads=1,
            batch_first=True
        )
        
    def forward(self, x, return_contention=False):
        """
        x: (batch_size, input_dim)
        Returns: predicted latency
        """
        # Split features
        density = x[:, 0:1]
        recent_latency = x[:, 1:2]
        diversity = x[:, 2:3]
        time_since_same = x[:, 3:4]
        task_onehot = x[:, 4:4+self.num_task_types]
        
        # Compute contention effect from task type
        # Task type influences others via contention matrix
        task_id = torch.argmax(task_onehot, dim=1)
        contention_effect = torch.zeros(x.size(0), 1, device=x.device)
        
        for i in range(x.size(0)):
            tid = task_id[i]
            # How much this task is affected by others (using recent density as proxy)
            contention_effect[i] = self.contention_matrix[tid].mean() * density[i]
        
        # Combine all features
        combined = torch.cat([
            density,
            recent_latency,
            diversity,
            time_since_same,
            contention_effect,
            task_onehot
        ], dim=1)
        
        # Predict latency
        latency = self.mlp(combined).squeeze()
        
        if return_contention:
            return latency, self.contention_matrix
        return latency

# ============================================
# 4. TRAINING LOOP
# ============================================

def train_model(model, X_train, y_train, X_val, y_val, epochs=200):
    """Train the contention predictor."""
    
    # Convert to tensors
    X_train_t = torch.tensor(X_train, dtype=torch.float32)
    y_train_t = torch.tensor(y_train, dtype=torch.float32)
    X_val_t = torch.tensor(X_val, dtype=torch.float32)
    y_val_t = torch.tensor(y_val, dtype=torch.float32)
    
    # Create data loaders
    train_dataset = torch.utils.data.TensorDataset(X_train_t, y_train_t)
    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
    
    # Optimizer and loss
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    criterion = nn.MSELoss()
    
    # Training history
    history = {'train_loss': [], 'val_loss': [], 'val_mae': []}
    
    for epoch in range(epochs):
        # Training
        model.train()
        train_loss = 0
        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            pred = model(batch_x)
            loss = criterion(pred, batch_y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
        
        train_loss /= len(train_loader)
        
        # Validation
        model.eval()
        with torch.no_grad():
            val_pred = model(X_val_t)
            val_loss = criterion(val_pred, y_val_t)
            val_mae = torch.mean(torch.abs(val_pred - y_val_t))
            
        scheduler.step(val_loss)
        
        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss.item())
        history['val_mae'].append(val_mae.item())
        
        if epoch % 20 == 0:
            print(f"Epoch {epoch:3d} | Train Loss: {train_loss:.2f} | Val Loss: {val_loss:.2f} | Val MAE: {val_mae:.2f} ms")
    
    return history

# Initialize and train model
input_dim = X_train.shape[1]
num_task_types = len(label_encoder.classes_)
model = ContentionPredictor(input_dim, hidden_dims=[64, 32], num_task_types=num_task_types)

print(f"\nTraining on {input_dim} features with {num_task_types} task types")
print("Model architecture:")
print(model)

history = train_model(model, X_train, y_train, X_val, y_val, epochs=100)

# ============================================
# 5. VISUALIZE RESULTS
# ============================================

# Plot training curves
fig, axes = plt.subplots(1, 3, figsize=(15, 4))

axes[0].plot(history['train_loss'], label='Train Loss')
axes[0].plot(history['val_loss'], label='Val Loss')
axes[0].set_xlabel('Epoch')
axes[0].set_ylabel('Loss (MSE)')
axes[0].set_title('Training Progress')
axes[0].legend()
axes[0].grid(True)

axes[1].plot(history['val_mae'])
axes[1].set_xlabel('Epoch')
axes[1].set_ylabel('MAE (ms)')
axes[1].set_title('Validation MAE')
axes[1].grid(True)

# Predictions vs actual
model.eval()
with torch.no_grad():
    y_pred = model(X_val_t).numpy()
    
axes[2].scatter(y_val, y_pred, alpha=0.5)
axes[2].plot([y_val.min(), y_val.max()], [y_val.min(), y_val.max()], 'r--', label='Perfect')
axes[2].set_xlabel('Actual Latency (ms)')
axes[2].set_ylabel('Predicted Latency (ms)')
axes[2].set_title('Predictions vs Actual')
axes[2].legend()
axes[2].grid(True)

plt.tight_layout()
plt.savefig('training_results.png', dpi=150)
plt.show()

# ============================================
# 6. LEARNED CONTENTION MATRIX VISUALIZATION
# ============================================

def visualize_contention_matrix(model, label_encoder):
    """Show the learned task interference patterns."""
    
    contention = model.contention_matrix.detach().numpy()
    
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(contention, cmap='RdBu_r', vmin=-0.5, vmax=0.5)
    
    # Labels
    task_names = [name.replace('-', '').strip()[:20] for name in label_encoder.classes_]
    ax.set_xticks(range(len(task_names)))
    ax.set_yticks(range(len(task_names)))
    ax.set_xticklabels(task_names, rotation=45, ha='right', fontsize=8)
    ax.set_yticklabels(task_names, fontsize=8)
    
    ax.set_xlabel('Task Type (j)')
    ax.set_ylabel('Task Type (i)')
    ax.set_title('Learned Contention Matrix: How task j affects task i')
    
    plt.colorbar(im, label='Contention Strength')
    plt.tight_layout()
    plt.savefig('contention_matrix.png', dpi=150)
    plt.show()
    
    # Print top interferences
    print("\nTop 5 learned interferences:")
    for i in range(contention.shape[0]):
        for j in range(contention.shape[1]):
            if i != j and abs(contention[i, j]) > 0.3:
                print(f"  {task_names[i]} ← {task_names[j]}: {contention[i, j]:.3f}")

visualize_contention_matrix(model, label_encoder)

# ============================================
# 7. SAVE MODEL FOR API
# ============================================

# Save everything needed for inference
torch.save({
    'model_state_dict': model.state_dict(),
    'scaler': scaler,
    'label_encoder': label_encoder,
    'feature_dim': input_dim,
    'contention_matrix': model.contention_matrix.detach().numpy()
}, 'contention_model.pth')

print("\n✅ Model saved to 'contention_model.pth'")
print(f"Training complete! Best validation MAE: {min(history['val_mae']):.2f} ms")

# ============================================
# 8. QUICK INFERENCE EXAMPLE
# ============================================

def predict_latency(task_type_str, recent_load=5, time_since_same=30):
    """Predict latency for a new task."""
    model.eval()
    
    # Encode task
    task_id = label_encoder.transform([task_type_str])[0]
    task_onehot = np.zeros(num_task_types)
    task_onehot[task_id] = 1
    
    # Build feature vector (matching training)
    features = np.array([
        recent_load / 60,  # density (tasks per sec)
        100,  # recent latency mean (placeholder)
        0.5,  # diversity (placeholder)
        min(time_since_same / 60, 1.0),  # time since same
        *task_onehot
    ]).reshape(1, -1)
    
    # Scale and predict
    features_scaled = scaler.transform(features)
    features_tensor = torch.tensor(features_scaled, dtype=torch.float32)
    
    with torch.no_grad():
        latency = model(features_tensor).item()
    
    return latency

# Test prediction
test_task = '-EG-RPTGSTEJECMES------------'
pred = predict_latency(test_task, recent_load=10, time_since_same=20)
print(f"\n🔮 Prediction for {test_task}: {pred:.0f} ms")