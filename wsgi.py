"""WSGI entry point para gunicorn en Render."""

from run import app, initialize_database

with app.app_context():
    initialize_database()

application = app
