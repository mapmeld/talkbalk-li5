import sys

import psycopg2
from psycopg2.extras import DictCursor
try:
    connection_string = sys.argv[1]
except:
    print('need a DB connection string')
conn = psycopg2.connect(connection_string)
cursor = conn.cursor(cursor_factory=DictCursor)

cursor.execute("""
CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    created BIGINT,
    updated BIGINT,
    text_type BOOLEAN
)
""")
conn.commit()
