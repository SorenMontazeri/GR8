import sqlite3
def runData():
    conn = sqlite3.connect("test.db")
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS test (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
    );
    """)
    testlist = ["Lukas", "Lisa", "Einar", "Cora"]
    cur.executemany("INSERT INTO test (name) VALUES (?);", [(name,) for name in testlist])


    conn.commit()
    conn.close()