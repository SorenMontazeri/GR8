import sqlite3

conn = sqlite3.connect("test.db")
cur = conn.cursor()
cur.execute("PRAGMA foreign_keys = ON;")
# 3) Skapa tabellen om den inte finns (bra vana)
cur.execute("""
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  age INTEGER NOT NULL
);
""")



conn.commit()
conn.close()