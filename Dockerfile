# Use an official Python runtime as a base image
FROM python:3.10-slim

# Set the working directory to /app
WORKDIR /app

# Copy only the necessary files
# COPY main.py ./
# COPY app ./app
# COPY rag ./rag
# COPY assets ./assets
# COPY store ./store
# COPY requirements.txt ./
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 5000 available to the world outside this container
EXPOSE 5050

# socketio.run() (i.e. "python main.py") uses Werkzeug's dev server, which
# Flask-SocketIO's own docs say isn't reliable for real WebSocket traffic
# (causes intermittent "write() before start_response" errors on upgrade).
# Gunicorn's threaded worker + simple-websocket is the documented production
# setup for async_mode="threading". Only 1 worker is supported here since
# session_service/the RAG engine singleton live in this process's memory.
CMD ["gunicorn", "-w", "1", "--threads", "100", "-b", "0.0.0.0:5050", "main:app"]

# COMMAND
# docker build -t aibackend .
# ** docker run --name aibackend -d -p 5001:5001 aibackend
# env var: docker run --name aibackend -p 5001:5001 -e VAR_NAME=value aibackend
# volume: docker run --name aibackend -p 5001:5001 -v /host/path:/container/path aibackend



