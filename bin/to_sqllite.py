#!/home/dvictoriano/Code/latency/env/bin/python3

import pandas as pd
import sqlite3


df = pd.read_csv('log_nav_2026.csv')

df['TIME'] = pd.to_datetime(
    df['TIME'],
    format="%Y-%m-%dT%H:%M:%S",
    errors="coerce"
)
df = df.sort_values('TIME')
#df = df.set_index('TIME')


# Create or open a database file
conn = sqlite3.connect('data.db')

# Create or open a database fil
cconn = sqlite3.connect(':memory:')

# Dump to SQLite
df.to_sql(
    name='latency',       # table name in SQLite
    con=conn,              # database connection
    if_exists='replace',   # options: 'fail', 'replace', 'append'
    index=False            # whether to write the DataFrame index as a column
)
