import os
from dotenv import load_dotenv

load_dotenv()

# Auth0 Configuration
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET")
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_CALLBACK_URL = os.getenv("AUTH0_CALLBACK_URL", "http://localhost:5000/callback")

# Flask Session Configuration
SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32))
