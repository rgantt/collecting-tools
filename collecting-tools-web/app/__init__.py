from flask import Flask
from pathlib import Path
from config import Config
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    from app.routes import main, update_url_params
    app.register_blueprint(main)
    app.template_filter('update_url_params')(update_url_params)

    # Re-enable auth
    from app.auth import auth_bp, oauth
    app.register_blueprint(auth_bp)
    oauth.init_app(app)

    # Add built-in functions to Jinja environment
    app.jinja_env.globals.update(min=min, max=max, range=range)

    return app
