import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit
import sqlite3

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET', 'fallback_secret')
socketio = SocketIO(app)

# --- GLOBAL STORAGE ---
current_state = {'mode': 'LANDING'} 
voted_ips = set() 

def connect_db():
    conn = sqlite3.connect('voting.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password')
        if password == os.getenv('ADMIN_PASSWORD'):
            session['logged_in'] = True
            return redirect(os.getenv('ADMIN_URL_PATH'))
        else:
            error = "Invalid Password"
    return render_template('login.html', error=error)

# --- NEW LOGOUT ROUTE ---
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route(os.getenv('ADMIN_URL_PATH', '/admin'))
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/vote')
def vote():
    return render_template('voter.html')

@app.route('/screen')
def screen():
    return render_template('screen.html')

# --- SOCKET EVENTS ---

@socketio.on('connect')
def handle_connect():
    client_ip = request.remote_addr
    emit('update_screen', {'mode': current_state['mode']})

    if client_ip in voted_ips:
        emit('vote_confirmed', {'success': False, 'message': 'You have already voted.'})

    if current_state['mode'] in ['VOTING', 'ENDED']:
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("SELECT id, name, yes_votes FROM contestants")
        rows = cur.fetchall()
        scores = {row['id']: {'name': row['name'], 'votes': row['yes_votes']} for row in rows}
        emit('update_scores', scores)

        if current_state['mode'] == 'VOTING' and client_ip not in voted_ips:
            cur.execute("SELECT id, name FROM contestants")
            contestants = [{'id': row['id'], 'name': row['name']} for row in cur.fetchall()]
            emit('voting_status', {'status': 'open', 'contestants': contestants})
        conn.close()

@socketio.on('show_landing')
def handle_show_landing():
    current_state['mode'] = 'LANDING'
    emit('update_screen', {'mode': 'LANDING'}, broadcast=True)
    emit('voting_status', {'status': 'closed'}, broadcast=True)

@socketio.on('open_voting_session')
def handle_open_voting():
    global voted_ips
    voted_ips.clear() 
    current_state['mode'] = 'VOTING'

    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM contestants")
    all_contestants = [{'id': row['id'], 'name': row['name']} for row in cur.fetchall()]
    cur.execute("SELECT id, name, yes_votes FROM contestants")
    rows = cur.fetchall()
    scores = {row['id']: {'name': row['name'], 'votes': row['yes_votes']} for row in rows}
    conn.close()
    
    emit('update_screen', {'mode': 'VOTING'}, broadcast=True)
    emit('voting_status', {'status': 'open', 'contestants': all_contestants}, broadcast=True)
    emit('update_scores', scores, broadcast=True)

@socketio.on('submit_votes')
def handle_vote_submission(data):
    client_ip = request.remote_addr
    if client_ip in voted_ips:
        emit('vote_confirmed', {'success': False, 'message': '⚠️ Error: You have already voted!'}, room=request.sid)
        return

    votes = data['votes']
    conn = connect_db()
    cur = conn.cursor()
    for c_id, vote_val in votes.items():
        if vote_val == 'yes':
            cur.execute("UPDATE contestants SET yes_votes = yes_votes + 1 WHERE id = ?", (c_id,))
        elif vote_val == 'no':
            cur.execute("UPDATE contestants SET no_votes = no_votes + 1 WHERE id = ?", (c_id,))
    conn.commit()
    
    cur.execute("SELECT id, name, yes_votes FROM contestants")
    rows = cur.fetchall()
    conn.close()

    scores = {}
    for row in rows:
        scores[row['id']] = {'name': row['name'], 'votes': row['yes_votes']}

    voted_ips.add(client_ip)
    emit('update_scores', scores, broadcast=True)
    emit('vote_confirmed', {'success': True, 'message': 'Votes Submitted Successfully!'}, room=request.sid)

@socketio.on('stop_voting')
def handle_stop_voting():
    current_state['mode'] = 'ENDED'
    emit('voting_status', {'status': 'closed'}, broadcast=True)
    emit('update_screen', {'mode': 'ENDED'}, broadcast=True)

@socketio.on('admin_reset_data')
def handle_reset_data():
    global voted_ips
    voted_ips.clear() 
    
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("UPDATE contestants SET yes_votes = 0, no_votes = 0")
    conn.commit()
    
    cur.execute("SELECT id, name, yes_votes FROM contestants")
    rows = cur.fetchall()
    scores = {row['id']: {'name': row['name'], 'votes': row['yes_votes']} for row in rows}
    conn.close()
    
    emit('update_scores', scores, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0')