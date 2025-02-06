import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

load_dotenv()

# Auth0 Configuration
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET")
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_CALLBACK_URL = os.getenv("AUTH0_CALLBACK_URL")

# Debug logging
logger.info("Auth0 Configuration:")
logger.info(f"Domain: {AUTH0_DOMAIN}")
logger.info(f"Client ID: {AUTH0_CLIENT_ID}")
logger.info(f"Callback URL: {AUTH0_CALLBACK_URL}")

# Flask Session Configuration
SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32))
