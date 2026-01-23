import time
from threading import Timer
from flask import Flask, render_template, request
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

# Track Yes and No separately
yes_counts = {c['id']: 0 for c in contestants}
no_counts = {c['id']: 0 for c in contestants}

# --- GLOBAL STATE ---
current_state = {
    "active_contestant_id": None,
    "active_contestant_name": "",
    "end_time": 0 
}

round_voters = set()

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('voter.html')

@app.route('/admin')
def admin():
    return render_template('admin.html', contestants=contestants)

@app.route('/screen')
def screen():
    return render_template('screen.html')

# --- HELPER: AUTO-CLOSE VOTING ---
def auto_close_voting():
    with app.app_context():
        if current_state['active_contestant_id'] is not None:
            stop_voting()

# --- SOCKET EVENTS ---

@socketio.on('connect')
def handle_connect():
    # Send only YES counts to the screen/user by default
    emit('update_scores', yes_counts)
    emit('state_change', current_state)
    
    if request.remote_addr in round_voters:
        emit('vote_success', {}, to=request.sid)

@socketio.on('admin_start_voting')
def start_voting(data):
    global round_voters
    c_id = int(data['id'])
    duration = int(data.get('seconds', 300)) 
    
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

@socketio.on('cast_vote')
def handle_vote(data):
    voter_ip = request.remote_addr
    vote_type = data.get('type', 'yes') # Default to 'yes' if missing
    
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
    
    # LOGIC: Track separately
    if vote_type == 'yes':
        yes_counts[c_id] += 1
    else:
        no_counts[c_id] += 1
        # We do NOT subtract from yes_counts
    
    round_voters.add(voter_ip)
    
    emit('vote_success', {}, to=request.sid)
    # Only broadcast the YES scores to the big screen
    emit('update_scores', yes_counts, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)