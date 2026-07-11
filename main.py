from flask import Flask
from flask_socketio import SocketIO
from app.api import api
from app.socket_events import register_socket_events
import os

app = Flask(__name__)

# Register the API blueprint
app.register_blueprint(api, url_prefix='/api')

# development mode and production mode
debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'

# cors_allowed_origins="*": the Unity client connects directly over WebSocket
# (no browser), so there's no Origin to allow-list against.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
register_socket_events(socketio)

@app.route("/")
def index():
    return "Hello World!"

if __name__ == "__main__":
    # 0.0.0.0 make flask use all available network interfaces
    # allow_unsafe_werkzeug: this is a LAN-only museum deployment run via
    # `python main.py`, not behind gunicorn/eventlet, so the dev server is
    # the production server here.
    socketio.run(app, host='0.0.0.0', port=5050, debug=debug_mode, allow_unsafe_werkzeug=True)