from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*"))

# In-memory storage for lobby participants
# Updated structure for lobbies
# Each lobby now includes a list of members and the admin's username
lobbies = {
    'Lobby 1': {'members': [], 'admin': ''},
    'Lobby 2': {'members': [], 'admin': ''},
    'Lobby 3': {'members': [], 'admin': ''}
}


# Utility functions for users and lobbies
def load_users():
    with open('users.json') as f:
        data = json.load(f)
    return data.get("users", [])

def save_user(users):
    with open('users.json', 'w') as f:
        json.dump({"users": users}, f)

@app.route('/')
def home():
    # Check if user is logged in already
    if session.get('logged_in'):
        # User is logged in, offer to go to select lobby or log out
        return render_template('welcome.html', logged_in=True)
    else:
        # User is not logged in, show the welcome page with login option
        return render_template('welcome.html', logged_in=False)


@app.route('/select_lobby', methods=['GET', 'POST'])
def select_lobby():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Handle Lobby Switching
        # Extract the previous lobby from the session
        previous_lobby = session.get('lobby', None)
        new_lobby_code = request.form.get('lobby_code').strip()
        new_lobby = 'Lobby ' + new_lobby_code if new_lobby_code else request.form.get('lobby')

        if previous_lobby and previous_lobby in lobbies and session['username'] in lobbies[previous_lobby]['members']:
            lobbies[previous_lobby]['members'].remove(session['username'])
            socketio.emit('lobby_updated', {'members': lobbies[previous_lobby]['members']}, room=previous_lobby)
            leave_room(previous_lobby)
        
        # Handle joining a new lobby
        lobby_code = request.form.get('lobby_code').strip()
        chosen_lobby = None
        if lobby_code:
            chosen_lobby = 'Lobby ' + lobby_code
            if chosen_lobby not in lobbies:
                lobbies[chosen_lobby] = {'members': [session['username']], 'admin': session['username']}
            elif session['username'] not in lobbies[chosen_lobby]['members']:
                lobbies[chosen_lobby]['members'].append(session['username'])
        else:
            chosen_lobby = request.form.get('lobby')
            if session['username'] not in lobbies[chosen_lobby]['members']:
                lobbies[chosen_lobby]['members'].append(session['username'])
        
        session['lobby'] = chosen_lobby
        # Emit the event after updating the lobby's members list
        # Modify the emit inside the select_lobby function and on_join function to include members list
        print(lobbies)
        print(session)
        socketio.emit('lobby_updated', {'members': lobbies[chosen_lobby]['members']}, room=chosen_lobby)
        return redirect(url_for('lobby', lobby_name=chosen_lobby))
    
    return render_template('select_lobby.html', lobbies=lobbies.keys())







@app.route('/lobby/<lobby_name>')
def lobby(lobby_name):
    if not session.get('logged_in') or 'lobby' not in session:
        return redirect(url_for('select_lobby'))
    lobby_info = lobbies.get(lobby_name, {})
    users_in_lobby = lobby_info.get('members', [])
    lobby_admin = lobby_info.get('admin', '')
    # Now passing both users_in_lobby and lobby_admin to the template
    return render_template('lobby.html', lobby_name=lobby_name, users=users_in_lobby, lobby_admin=lobby_admin)


# SocketIO event for joining a lobby
@socketio.on('join')
def on_join(data):
    lobby_name = data['lobby_name']
    join_room(lobby_name)
    # If needed, emit the current state to just the user who joined
    emit('lobby_updated', {'members': lobbies[lobby_name]['members']}, to=request.sid)



@app.route('/check_membership/<lobby_name>')
def check_membership(lobby_name):
    if 'username' in session and 'lobby' in session:
        is_member = session['username'] in lobbies.get(lobby_name, {}).get('members', [])
        return jsonify(is_member=is_member)
    return jsonify(is_member=False)



@app.route('/remove_user/<lobby_name>/<username>', methods=['POST'])
def remove_user(lobby_name, username):
    if 'logged_in' in session and session['username'] == lobbies[lobby_name]['admin']:
        if username in lobbies[lobby_name]['members']:
            print(lobbies)
            lobbies[lobby_name]['members'].remove(username)
            # Broadcast updated lobby members
            socketio.emit('lobby_updated', {
                'members': lobbies[lobby_name]['members'],
                'admin': lobbies[lobby_name]['admin']
            }, room=lobby_name)
            # Notify the removed user if online
            print(lobbies)
            return jsonify({'success': True})
    return jsonify({'success': False}), 403



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        users = load_users()
        user = next((user for user in users if user['username'] == username), None)

        if user and user['password'] == password:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('select_lobby'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']  # Save the password directly without hashing

        users = load_users()

        if any(user['username'] == username for user in users):
            flash('Username already exists.')
        else:
            users.append({"username": username, "password": password})
            save_user(users)
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
def logout():
    current_lobby = session.get('lobby')
    if current_lobby and session['username'] in lobbies[current_lobby]['members']:
        lobbies[current_lobby]['members'].remove(session['username'])
        socketio.emit('lobby_updated', {'members': lobbies[current_lobby]['members']}, room=current_lobby)
        leave_room(current_lobby)

    session.clear()
    return redirect(url_for('home'))


@socketio.on('disconnect')
def handle_disconnect():
    username = session.get('username')
    current_lobby = session.get('lobby')
    if current_lobby and username and username in lobbies[current_lobby]['members']:
        lobbies[current_lobby]['members'].remove(username)
        socketio.emit('lobby_updated', {'members': lobbies[current_lobby]['members']}, room=current_lobby)
        leave_room(current_lobby)
        






@socketio.on('switch_page', namespace='/lobby')
def handle_switch_page(message):
    print(f"Switching page to: {message['new_page']}")
    emit('page_switched', {'new_page': message['new_page']}, room=message['lobby_name'], include_self=True, namespace='/lobby')








if __name__ == '__main__':
    socketio.run(app, debug=True)

