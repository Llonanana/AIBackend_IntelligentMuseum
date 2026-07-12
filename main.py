import logging

# Configure the root logger here, before anything else, so it already has a
# handler by the time any library lazily checks "does root have a handler yet?"
# and adds its own if not. Under gunicorn's threaded worker, two concurrent
# requests could both hit that lazy check at once and each add their own
# handler, which is why log lines were getting printed twice.
logging.basicConfig(level=logging.WARNING)

from flask import Flask
from flask_socketio import SocketIO
from app.api import api
from app.socket_events import register_socket_events
import os

# openai/httpx log every HTTP request at INFO level, which would otherwise add
# noise on top of our own logging once they propagate to root.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

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
    # Only used for `python main.py` local runs outside Docker. The container
    # instead runs gunicorn against main:app directly (see Dockerfile) since
    # Werkzeug's dev server isn't reliable for WebSocket traffic.
    # 0.0.0.0 make flask use all available network interfaces
    socketio.run(app, host='0.0.0.0', port=5050, debug=debug_mode, allow_unsafe_werkzeug=True)