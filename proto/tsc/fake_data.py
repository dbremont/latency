"""
Let's generate some fake data set of the form:

Pandas Data Frame:

1. Time (Datetime)
2. Value (float)

Sample:
Time,Value
2026-02-27 12:00:01.311800615,120.31397249473976
2026-02-27 12:00:02.186006429,116.80180437241344
2026-02-27 12:00:05.962595847,86.43432174611584
2026-02-27 12:00:06.152266039,107.89852060155383
2026-02-27 12:00:06.873089205,104.52823774391885
"""

import pandas as pd
import numpy as np
import sqlite3

# Parameters
n = 1_000_000  # number of observations
start_time = pd.Timestamp('2026-02-27 12:00:00')
end_time = pd.Timestamp('2026-03-27 13:00:00')

# Generate random timestamps between start and end
np.random.seed(42)  # reproducibility
random_seconds = np.random.uniform(0, (end_time - start_time).total_seconds(), n)
random_microseconds = np.random.randint(0, 1000*1000, n)  # random microseconds

time_series = [start_time + pd.Timedelta(seconds=s, microseconds=us)
               for s, us in zip(random_seconds, random_microseconds)]

# Generate random float values (simulating latency)
values = np.random.normal(loc=100, scale=10, size=n)

# Create DataFrame
df = pd.DataFrame({
    'Time': time_series,
    'Value': values
})

# Sort by time (optional, makes analysis easier)
df = df.sort_values('Time').reset_index(drop=True)

df.to_csv('data/latency.csv', index=False)

# Connect to (or create) a SQLite database
conn = sqlite3.connect('data/data.db')  # database file will be created if it doesn't exist

df.to_sql('latency', conn, if_exists='replace', index=False)

conn.close()
