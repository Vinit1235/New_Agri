import sqlite3

conn = sqlite3.connect('soiledge.db')
cursor = conn.cursor()

# Check automation_events columns
cursor.execute('PRAGMA table_info(automation_events)')
cols = [row[1] for row in cursor.fetchall()]
print('automation_events existing cols:', cols)

for col, ctype in [('flow_rate_lpm', 'FLOAT'), ('session_volume_L', 'FLOAT'), ('total_volume_L', 'FLOAT')]:
    if col not in cols:
        print(f'Adding {col} to automation_events')
        cursor.execute(f'ALTER TABLE automation_events ADD COLUMN "{col}" {ctype}')

# Check sensor_readings columns
cursor.execute('PRAGMA table_info(sensor_readings)')
r_cols = [row[1] for row in cursor.fetchall()]
print('sensor_readings existing cols:', r_cols)

for col, ctype in [('turbidity_ntu', 'FLOAT'), ('flow_rate_lpm', 'FLOAT'), ('session_volume_L', 'FLOAT'), ('total_volume_L', 'FLOAT')]:
    if col not in r_cols:
        print(f'Adding {col} to sensor_readings')
        cursor.execute(f'ALTER TABLE sensor_readings ADD COLUMN "{col}" {ctype}')

conn.commit()
conn.close()
print('Migration complete!')
