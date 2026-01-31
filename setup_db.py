import sqlite3

def init_db():
    conn = sqlite3.connect('voting.db')
    cur = conn.cursor()

    # 1. Create the table if it doesn't exist
    cur.execute('''
        CREATE TABLE IF NOT EXISTS contestants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            yes_votes INTEGER DEFAULT 0,
            no_votes INTEGER DEFAULT 0
        )
    ''')

    # 2. Add some dummy contestants (Optional - prevents empty table error)
    # Check if table is empty first
    cur.execute('SELECT count(*) FROM contestants')
    count = cur.fetchone()[0]
    
    if count == 0:
        print("Adding sample contestants...")
        contestants = [
            ('Alice', 0, 0),
            ('Bob', 0, 0),
            ('Charlie', 0, 0)
        ]
        cur.executemany('INSERT INTO contestants (name, yes_votes, no_votes) VALUES (?, ?, ?)', contestants)
        conn.commit()
    else:
        print("Table already has data. Skipping insertion.")

    conn.close()
    print("Database initialized successfully!")

if __name__ == '__main__':
    init_db()