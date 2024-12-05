from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import os
import json
from Crypto.Random import random
import ssl

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", transports=['websocket', 'polling'])  # Enable SocketIO

# File paths
VOTERS_FILE = "voters.json"
VOTES_FILE = "votes.json"
USED_TOKENS_FILE = "used_tokens.json"
REPRESENTATIVES = ["Rep A", "Rep B", "Rep C"]

# Initialize storage
if not os.path.exists(VOTERS_FILE):
    with open(VOTERS_FILE, "w") as f:
        json.dump({}, f)

if not os.path.exists(VOTES_FILE):
    with open(VOTES_FILE, "w") as f:
        json.dump({rep: 0 for rep in REPRESENTATIVES}, f)

if not os.path.exists(USED_TOKENS_FILE):
    with open(USED_TOKENS_FILE, "w") as f:
        json.dump([], f)


@app.route('/authenticate', methods=['POST'])
def authenticate():
    """
    Authenticate voter and issue a one-time token for voting.
    """
    data = request.get_json()
    voter_id = data.get("voter_id")
    otp = data.get("otp")  # OTP assumed to be validated externally

    if not voter_id or not otp:
        return jsonify({"error": "Missing voter ID or OTP"}), 400

    with open(VOTERS_FILE, "r+") as f:
        voters = json.load(f)
        if voter_id in voters:
            return jsonify({"error": "Voter has already authenticated"}), 400

        # Generate a one-time token
        token = str(random.getrandbits(128))
        voters[voter_id] = token
        f.seek(0)
        json.dump(voters, f)
        f.truncate()

    return jsonify({"token": token}), 200


@app.route('/vote', methods=['POST'])
def vote():
    """
    Submit a vote anonymously.
    """
    data = request.get_json()
    token = data.get("token")
    vote = data.get("vote")

    if not token or not vote:
        return jsonify({"error": "Missing token or vote"}), 400

    if vote not in REPRESENTATIVES:
        return jsonify({"error": "Invalid vote"}), 400

    with open(VOTERS_FILE, "r") as f:
        voters = json.load(f)

    # Verify if the token is valid
    if token not in voters.values():
        return jsonify({"error": "Invalid or already used token"}), 400

    # Mark the token as used
    with open(USED_TOKENS_FILE, "r+") as f:
        used_tokens = json.load(f)
        if token in used_tokens:
            return jsonify({"error": "This token has already been used"}), 400

        used_tokens.append(token)
        f.seek(0)
        json.dump(used_tokens, f)
        f.truncate()

    # Record the vote anonymously
    with open(VOTES_FILE, "r+") as f:
        votes = json.load(f)
        votes[vote] += 1
        f.seek(0)
        json.dump(votes, f)
        f.truncate()

    # Emit updated results to all connected clients
    with open(VOTES_FILE, "r") as f:
        votes = json.load(f)
        socketio.emit('update_results', votes)  # Send real-time update

    return jsonify({"message": "Vote submitted successfully"}), 200


@app.route('/results', methods=['GET'])
def result():
    """
    Return real-time vote count.
    """
    with open(VOTES_FILE, "r") as f:
        votes = json.load(f)
    print(votes)
    return jsonify(votes), 200


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection and emit the current vote count"""
    print("Client connected to /result")
    
    # Send current results to the client when they first connect
    with open(VOTES_FILE, "r") as f:
        votes = json.load(f)
        emit('update_results', votes)  # Emit current vote counts to the client


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    print("Client disconnected from /result")

if __name__ == "__main__":
    # from gevent.pywsgi import WSGIServer
    # from geventwebsocket.handler import WebSocketHandler

    # # Configure SSL
    # context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # context.load_cert_chain(certfile='server.crt', keyfile='server.key')

    # Create and run the WSGIServer
    # http_server = WSGIServer(('0.0.0.0', 5000), app, handler_class=WebSocketHandler, ssl_context=context)
    # http_server.serve_forever()


    # socketio.run(app, host="0.0.0.0", port="5000", debug=True, ssl_context=('server.crt', 'server.key'))


    import eventlet
    eventlet.wsgi.server(
        eventlet.wrap_ssl(
            eventlet.listen(('0.0.0.0', 5000)),
            certfile='server.crt',
            keyfile='server.key',
            server_side=True,
        ),
        app,
    )