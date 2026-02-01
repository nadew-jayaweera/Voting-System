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
        print("Adding contestants...")
        contestants = [
            ('Khadeeja Mohamed Ashraff', 0, 0),
            ('Tharanjee Dahanayaka', 0, 0),
            ('S.D. Thalpawila', 0, 0),
            ('Teesha Hewa Matarage', 0, 0),
            ('Gallala Gamage Lakna Hansinee', 0, 0),
            ('K.A.D.S. Jayalath', 0, 0),
            ('E.A.T.K. Athukorala', 0, 0),
            ('K.A. Hiruni Pabasara Warnasekara', 0, 0),
            ('W.M.R.L. Walisundara', 0, 0),
            ('V. Lochini Weerasekara', 0, 0),
            ('U.L.C. Bhashitha', 0, 0),
            ('Posandu Mapa', 0, 0)
        ]
        cur.executemany('INSERT INTO contestants (name, yes_votes, no_votes) VALUES (?, ?, ?)', contestants)
        conn.commit()
    else:
        print("Table already has data. Skipping insertion.")

    conn.close()
    print("Database initialized successfully!")

if __name__ == '__main__':
    init_db()