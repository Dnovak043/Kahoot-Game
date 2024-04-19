from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

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



def load_quizzes():
    try:
        with open('quizzes.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {'quizzes': []}  # Return empty list if file not found



def save_quizzes(quizzes):
    print("SAVING QUIZZES")
    with open('quizzes.json', 'w') as file:
        json.dump(quizzes, file, indent=4)






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
    
    
    quizzes = load_quizzes()
    print(quizzes)
    owned_quizzes = [quiz for quiz in quizzes['quizzes'] if quiz['owner'] == session['username']]
    print(session['username'])
    print(owned_quizzes)
        
    
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
            chosen_lobby = lobby_code
            if chosen_lobby not in lobbies:
                lobbies[chosen_lobby] = {'members': [session['username']], 'admin': session['username']}
            elif session['username'] not in lobbies[chosen_lobby]['members']:
                lobbies[chosen_lobby]['members'].append(session['username'])
                
                
                # Find the corresponding quiz
                quiz = next((q for q in quizzes['quizzes'] if q['quiz_id'] == chosen_lobby), None)
                if not quiz['owner'] == session['username']:
                    if quiz:
                        # Now find the participant
                        participant = next((p for p in quiz['participants'] if (p['username'] == session['username'])), None)
                        
                        if not participant :
                            # Initialize and add the participant if they don't exist
                            participant = {
                                'username': session['username'],
                                'responses': [{'question_id': i + 1, 'selected_option': -1} for i, _ in enumerate(quiz['questions'])],
                                'score': 0  # Initialize score
                            }
                            quiz['participants'].append(participant)
                            save_quizzes(quizzes)  # Save updates to file or database

                
                
        else:
            chosen_lobby = request.form.get('lobby')
            if session['username'] not in lobbies[chosen_lobby]['members']:
                lobbies[chosen_lobby]['members'].append(session['username'])
                
                
                # Find the corresponding quiz
                quiz = next((q for q in quizzes['quizzes'] if q['quiz_id'] == chosen_lobby), None)
                if not quiz['owner'] == session['username']:
                    if quiz:
                        # Now find the participant
                        participant = next((p for p in quiz['participants'] if (p['username'] == session['username'])), None)
                        
                        if not participant :
                            # Initialize and add the participant if they don't exist
                            participant = {
                                'username': session['username'],
                                'responses': [{'question_id': i + 1, 'selected_option': -1} for i, _ in enumerate(quiz['questions'])],
                                'score': 0  # Initialize score
                            }
                            quiz['participants'].append(participant)
                            save_quizzes(quizzes)  # Save updates to file or database
            
        session['lobby'] = chosen_lobby
        # Emit the event after updating the lobby's members list
        # Modify the emit inside the select_lobby function and on_join function to include members list
        print(lobbies)
        print(session)
        socketio.emit('lobby_updated', {'members': lobbies[chosen_lobby]['members']}, room=chosen_lobby)
        return redirect(url_for('lobby', lobby_name=chosen_lobby))
    
    return render_template('select_lobby.html', lobbies=lobbies.keys(), quizzes=owned_quizzes)






@app.route('/lobby/<lobby_name>')
def lobby(lobby_name):
    if not session.get('logged_in') or 'lobby' not in session:
        return redirect(url_for('select_lobby'))
    lobby_info = lobbies.get(lobby_name, {})
    users_in_lobby = lobby_info.get('members', [])
    lobby_admin = lobby_info.get('admin', '')
    quizzes = load_quizzes()
    lobby_quiz = next((quiz for quiz in quizzes['quizzes'] if quiz['quiz_id'] == lobby_name), None)
    print(lobby_quiz)

    
    # Now passing both users_in_lobby and lobby_admin to the template
    return render_template('lobby.html', lobby_name=lobby_name, users=users_in_lobby, lobby_admin=lobby_admin, quiz=lobby_quiz)


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
        


@socketio.on('page_change')
def handle_page_change(data):
    lobby_name = data['lobby_name']
    new_page = data['newPage']
    
    
    # Verify if the user is the admin before broadcasting
    if 'logged_in' in session and session['username'] == lobbies[lobby_name]['admin']:
        print("CHANGING PAGE")
        emit('change_page', {'newPage': new_page}, to=lobby_name)



@socketio.on('submit_answer')
def submit_answer(data):
    username = session['username']
    question_id = data['question_id']
    selected_option = data['selected_option']
    quiz_id = data['quiz_id']

    # Load quizzes and find the correct quiz and participant
    quizzes = load_quizzes()
    quiz = next((q for q in quizzes['quizzes'] if q['quiz_id'] == quiz_id), None)
    if quiz:
        participant = next((p for p in quiz['participants'] if p['username'] == username), None)
        if participant:
            # Find the correct response index and update it
            response = next((r for r in participant['responses'] if r['question_id'] == question_id), None)
            if response:
                response['selected_option'] = selected_option
            else:
                participant['responses'].append({
                    'question_id': question_id,
                    'selected_option': selected_option,
                })
            
            print(quiz['questions'][question_id - 1]['correct_answer'])
            print(selected_option == quiz['questions'][question_id - 1]['correct_answer'])
            print(participant['score'])
            
            if selected_option == quiz['questions'][question_id - 1]['correct_answer']:
                participant['score'] = participant['score'] + 1
            
            save_quizzes(quizzes)
            
        emit('answer_received', {'status': 'success', 'question_id': question_id, 'username': username}, broadcast=True)




######### QUIZZES #########

# @app.route('/submit_answer', methods=['POST'])
# def submit_answer():
#     question_id = request.form.get('question_id')
#     selected_answer = request.form.get('selected_answer')
    
#     print(session['username'])
#     print(question_id)
#     print(selected_answer)
#     print()
#     # Process the answer, e.g., record it, check if it's correct, etc.
#     # Redirect or return a result page
#     #return redirect(url_for('result_page'))  # Redirect to a result or next question page

@app.route('/create_quiz' , methods=['GET', 'POST'])
def create_quiz():
    if request.method == 'POST':
        quiz_name = request.form['quiz_name']
        owner = session['username']
        questions = request.form.getlist('questions[]')
        times = request.form.getlist('times[]')
        answers = [request.form.getlist('answers_{}[]'.format(i)) for i in range(len(questions))]
        correct = [request.form.getlist('correct_{}[]'.format(i)) for i in range(len(questions))]

        quiz = {
            'quiz_id': quiz_name,
            'owner': owner,
            'participants': [],
            'questions': [
                {
                    'question': questions[i],
                    'options': answers[i],
                    'correct_answer': answers[i][int(correct[i][0])],
                    'time': int(times[i])
                } for i in range(len(questions))
            ]
        }

        quizzes = load_quizzes()
        quizzes['quizzes'].append(quiz)
        save_quizzes(quizzes)
        return redirect(url_for('select_lobby'))
    return render_template('create_quiz.html')

def update_score(quiz_id, username, new_score):
    quizzes = load_quizzes()
    for quiz in quizzes['quizzes']:
        if quiz['quiz_id'] == quiz_id:
            for participant in quiz['participants']:
                if participant['username'] == username:
                    participant['score'] = new_score
                    break
    save_quizzes(quizzes)












if __name__ == '__main__':
    socketio.run(app, debug=True)

