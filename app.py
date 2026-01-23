import time
import sqlite3
import pandas as pd
from threading import Timer
from flask import Flask, render_template, request, send_file
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- DATA ---
contestants = [
    {"id": 1, "name": "Contestant 1"},
    {"id": 2, "name": "Contestant 2"},
    {"id": 3, "name": "Contestant 3"},
    {"id": 4, "name": "Contestant 4"}
]

# --- DATABASE SETUP ---
DB_NAME = "voting.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS votes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  contestant_id INTEGER,
                  contestant_name TEXT,
                  vote_type TEXT,
                  voter_ip TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# --- GLOBAL STATE ---
yes_counts = {c['id']: 0 for c in contestants}
no_counts = {c['id']: 0 for c in contestants}

current_state = {
    "active_contestant_id": None,
    "active_contestant_name": "",
    "end_time": 0 
}

round_voters = set()

# --- HELPER: GET REAL IP (FIX FOR NGROK) ---
def get_client_ip():
    """
    Retrieves the real IP address of the user, even if they are behind 
    a proxy like Ngrok, Cloudflare, or Render.
    """
    if 'X-Forwarded-For' in request.headers:
        # The header often looks like: "Client-IP, Proxy-IP, ..."
        # We want the first one (the Client).
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/vote')
def vote():
    return render_template('voter.html')

@app.route('/admin')
def admin():
    return render_template('admin.html', contestants=contestants)

@app.route('/screen')
def screen():
    return render_template('screen.html')

@app.route('/export')
def export_results():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM votes", conn)
    conn.close()

    if df.empty:
        return "No votes recorded yet!"

    summary = df.pivot_table(
        index='contestant_name', 
        columns='vote_type', 
        values='id', 
        aggfunc='count', 
        fill_value=0
    )
    summary['Total Votes'] = summary.get('yes', 0) + summary.get('no', 0)

    filename = "Competition_Results.xlsx"
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        summary.to_excel(writer, sheet_name='Summary Table')
        df.to_excel(writer, sheet_name='Raw Audit Log', index=False)
        
    return send_file(filename, as_attachment=True)

# --- HELPERS ---
def auto_close_voting():
    with app.app_context():
        if current_state['active_contestant_id'] is not None:
            stop_voting()

# --- SOCKET EVENTS ---

@socketio.on('connect')
def handle_connect():
    # Use the new IP helper here too!
    user_ip = get_client_ip()
    
    emit('update_scores', yes_counts)
    emit('state_change', current_state)
    
    if user_ip in round_voters:
        emit('vote_success', {}, to=request.sid)

@socketio.on('admin_start_voting')
def start_voting(data):
    global round_voters
    c_id = int(data['id'])
    duration = int(data.get('seconds', 1800)) 
    
    c_name = next((c['name'] for c in contestants if c['id'] == c_id), "Unknown")

    current_state['active_contestant_id'] = c_id
    current_state['active_contestant_name'] = c_name
    current_state['end_time'] = time.time() + duration 
    
    round_voters.clear()

    emit('state_change', current_state, broadcast=True)
    t = Timer(duration, auto_close_voting)
    t.start()

@socketio.on('admin_stop_voting')
def stop_voting():
    current_state['active_contestant_id'] = None
    current_state['active_contestant_name'] = ""
    current_state['end_time'] = 0
    emit('state_change', current_state, broadcast=True)

@socketio.on('admin_reset_data')
def reset_data():
    global yes_counts, no_counts, round_voters
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM votes") 
    conn.commit()
    conn.close()

    yes_counts = {c['id']: 0 for c in contestants}
    no_counts = {c['id']: 0 for c in contestants}
    round_voters.clear()
    
    stop_voting() 
    emit('update_scores', yes_counts, broadcast=True)

@socketio.on('cast_vote')
def handle_vote(data):
    # --- CRITICAL FIX: Use the helper function ---
    voter_ip = get_client_ip()
    # ---------------------------------------------

    vote_type = data.get('type', 'yes') 
    
    if current_state['active_contestant_id'] is None:
        return 
    
    if time.time() > current_state['end_time']:
        emit('vote_error', {'msg': 'Voting session expired'}, to=request.sid)
        stop_voting()
        return

    if voter_ip in round_voters:
        emit('vote_error', {'msg': 'Already voted!'}, to=request.sid)
        return

    c_id = current_state['active_contestant_id']
    c_name = current_state['active_contestant_name']
    
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO votes (contestant_id, contestant_name, vote_type, voter_ip) VALUES (?, ?, ?, ?)", 
                  (c_id, c_name, vote_type, voter_ip))
        conn.commit()
        conn.close()
    except Exception as e:
        print("DB Error:", e)

    if vote_type == 'yes':
        yes_counts[c_id] += 1
    else:
        no_counts[c_id] += 1
    
    round_voters.add(voter_ip)
    
    emit('vote_success', {}, to=request.sid)
    emit('update_scores', yes_counts, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)