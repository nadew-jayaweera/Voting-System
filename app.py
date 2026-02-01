import os
import uuid
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_socketio import SocketIO, emit
import sqlite3
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from datetime import datetime
import io

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET', 'fallback_secret')
socketio = SocketIO(app)

# --- GLOBAL STORAGE ---
current_state = {'mode': 'LANDING'}
voted_voter_ids = set()

def get_voter_id():
    if 'voter_id' not in session:
        session['voter_id'] = uuid.uuid4().hex
    return session['voter_id']

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
    get_voter_id()
    return render_template('voter.html')

@app.route('/screen')
def screen():
    return render_template('screen.html')

@app.route('/export_votes')
def export_votes():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Voting Results"
    
    ws['A1'] = 'Voting System - Results Export'
    ws['A1'].font = Font(size=16, bold=True, color="FFFFFF")
    ws['A1'].fill = PatternFill(start_color="667eea", end_color="667eea", fill_type="solid")
    ws['A1'].alignment = Alignment(horizontal="center")
    ws.merge_cells('A1:D1')
    
    ws['A2'] = f'Exported on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
    ws.merge_cells('A2:D2')
    
    headers = ['ID', 'Contestant Name', 'Yes Votes', 'No Votes']
    ws.append([])
    ws.append(headers)
    
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, yes_votes, no_votes FROM contestants ORDER BY yes_votes DESC")
    rows = cur.fetchall()
    conn.close()
    
    for row in rows:
        ws.append([row['id'], row['name'], row['yes_votes'], row['no_votes']])
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'voting_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )

# --- SOCKET EVENTS ---

@socketio.on('connect')
def handle_connect():
    voter_id = session.get('voter_id')
    emit('update_screen', {'mode': current_state['mode']})

    # If already voted (based on session ID), tell them immediately
    if voter_id and voter_id in voted_voter_ids:
        emit('vote_confirmed', {'success': False, 'message': 'You have already voted.'})

    if current_state['mode'] == 'LANDING':
        emit('voting_status', {'status': 'waiting'})
    elif current_state['mode'] in ['VOTING', 'STOPPED', 'ENDED']:
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("SELECT id, name, yes_votes FROM contestants")
        rows = cur.fetchall()
        scores = {row['id']: {'name': row['name'], 'votes': row['yes_votes']} for row in rows}
        emit('update_scores', scores)

        if current_state['mode'] == 'VOTING' and (not voter_id or voter_id not in voted_voter_ids):
            cur.execute("SELECT id, name FROM contestants")
            contestants = [{'id': row['id'], 'name': row['name']} for row in cur.fetchall()]
            emit('voting_status', {'status': 'open', 'contestants': contestants})
        elif current_state['mode'] in ['STOPPED', 'ENDED']:
            emit('voting_status', {'status': 'closed'})
        conn.close()

@socketio.on('show_landing')
def handle_show_landing():
    current_state['mode'] = 'LANDING'
    emit('update_screen', {'mode': 'LANDING'}, broadcast=True)
    emit('voting_status', {'status': 'waiting'}, broadcast=True)

@socketio.on('open_voting_session')
def handle_open_voting():
    # Note: open_voting_session does NOT clear history. 
    # Use reset button for that.
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
    voter_id = get_voter_id()
    
    # Server-Side Check
    if voter_id in voted_voter_ids:
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
    scores = {row['id']: {'name': row['name'], 'votes': row['yes_votes']} for row in rows}
    conn.close()

    voted_voter_ids.add(voter_id)
    
    emit('update_scores', scores, broadcast=True)
    emit('vote_confirmed', {'success': True, 'message': 'Votes Submitted Successfully!'}, room=request.sid)

@socketio.on('stop_voting')
def handle_stop_voting():
    current_state['mode'] = 'STOPPED'
    emit('voting_status', {'status': 'closed'}, broadcast=True)
    emit('update_screen', {'mode': 'STOPPED'}, broadcast=True)
    
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, yes_votes FROM contestants")
    rows = cur.fetchall()
    scores = {row['id']: {'name': row['name'], 'votes': row['yes_votes']} for row in rows}
    conn.close()
    emit('update_scores', scores, broadcast=True)

@socketio.on('admin_reset_data')
def handle_reset_data():
    global voted_voter_ids
    voted_voter_ids.clear()
    
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("UPDATE contestants SET yes_votes = 0, no_votes = 0")
    conn.commit()
    
    cur.execute("SELECT id, name, yes_votes FROM contestants")
    rows = cur.fetchall()
    scores = {row['id']: {'name': row['name'], 'votes': row['yes_votes']} for row in rows}
    conn.close()
    
    emit('update_scores', scores, broadcast=True)
    
    # --- IMPORTANT: Clears the client-side stamp ---
    emit('system_reset', broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=False, host='0.0.0.0')