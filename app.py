import time
import os
import sqlite3
import pandas as pd
from threading import Timer
from flask import Flask, render_template, request, send_file, redirect, url_for, session, flash, make_response
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

# 1. LOAD SECRETS
load_dotenv()

app = Flask(__name__)
# Ensure Secret Key is consistent.
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET', 'fallback_fixed_key_999')
socketio = SocketIO(app, cors_allowed_origins="*")

# 2. GET CONFIG FROM .ENV
ADMIN_PASSWORD = (os.getenv('ADMIN_PASSWORD') or "1234").strip()
ADMIN_PATH = (os.getenv('ADMIN_URL_PATH') or "/admin").strip()

# --- DATA ---
contestants = [
    {"id": 1, "name": "Khadeeja Mohamed Ashraff"},
    {"id": 2, "name": "Tharanjee Dahanayaka"},
    {"id": 3, "name": "S.D. Thalpawila"},
    {"id": 4, "name": "Teesha Hewa Matarage"},
    {"id": 5, "name": "Gallala Gamage Lakna Hansinee"},
    {"id": 6, "name": "K.A.D.S. Jayalath"},
    {"id": 7, "name": "E.A.T.K. Athukorala"},
    {"id": 8, "name": "K.A. Hiruni Pabasara Warnasekara"},
    {"id": 9, "name": "W.M.R.L. Walisundara"},
    {"id": 10, "name": "V. Lochini Weerasekara"},
    {"id": 11, "name": "U.L.C. Bhashitha"},
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

# Create a mapping of contestant IDs to names
contestant_names = {c['id']: c['name'] for c in contestants}

current_state = {
    "active_contestant_id": None,
    "active_contestant_name": "",
    "end_time": 0 
}

round_voters = set()

# --- HELPER: GET REAL IP ---
def get_client_ip():
    if 'X-Forwarded-For' in request.headers:
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

# --- HELPER: GET SCORES WITH NAMES ---
def get_scores_with_names():
    """Return scores with contestant names for frontend display"""
    scores_data = {}
    for c_id, count in yes_counts.items():
        name = contestant_names.get(c_id, f'C{c_id}')
        scores_data[c_id] = {
            'name': name,
            'votes': count
        }
    return scores_data

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/vote')
def vote():
    return render_template('voter.html')

@app.route('/screen')
def screen():
    return render_template('screen.html')

# --- LOGIN SYSTEM ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, send them straight to admin
    if session.get('is_admin'):
        return redirect(ADMIN_PATH)

    if request.method == 'POST':
        password_input = (request.form.get('password') or "").strip()
        
        if password_input == ADMIN_PASSWORD:
            session['is_admin'] = True
            session.permanent = True  # Keep logged in (until logout)
            return redirect(ADMIN_PATH)
        else:
            flash('Invalid Password')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear() # Destroy the "VIP Pass"
    return redirect(url_for('login'))

# --- THE HIDDEN ADMIN ROUTE ---
@app.route(ADMIN_PATH)
def admin_panel():
    # SECURITY CHECK
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    # RENDER WITH NO CACHE (Security Fix)
    # This prevents the "Back Button" from showing the page after logout
    response = make_response(render_template('admin.html', contestants=contestants))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/export')
def export_results():
    if not session.get('is_admin'):
        return redirect(url_for('login'))

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

# --- SOCKET EVENTS ---

def auto_close_voting():
    with app.app_context():
        if current_state['active_contestant_id'] is not None:
            stop_voting()

@socketio.on('connect')
def handle_connect():
    user_ip = get_client_ip()
    emit('update_scores', get_scores_with_names())
    emit('state_change', current_state)
    if user_ip in round_voters:
        emit('vote_success', {}, to=request.sid)

@socketio.on('admin_start_voting')
def start_voting(data):
    if not session.get('is_admin'): return 
    
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
    if not session.get('is_admin'): return 

    current_state['active_contestant_id'] = None
    current_state['active_contestant_name'] = ""
    current_state['end_time'] = 0
    emit('state_change', current_state, broadcast=True)

@socketio.on('admin_reset_data')
def reset_data():
    if not session.get('is_admin'): return 

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
    emit('update_scores', get_scores_with_names(), broadcast=True)

@socketio.on('cast_vote')
def handle_vote(data):
    voter_ip = get_client_ip()
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
    emit('update_scores', get_scores_with_names(), broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)