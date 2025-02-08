from functools import wraps
from flask import Blueprint, session, redirect, url_for, request
from authlib.integrations.flask_client import OAuth
from urllib.parse import urlencode
import json
from .auth_config import (
    AUTH0_CLIENT_ID,
    AUTH0_CLIENT_SECRET,
    AUTH0_DOMAIN
)

auth_bp = Blueprint('auth', __name__)
oauth = OAuth()

oauth.register(
    "auth0",
    client_id=AUTH0_CLIENT_ID,
    client_secret=AUTH0_CLIENT_SECRET,
    client_kwargs={
        "scope": "openid profile email",
    },
    server_metadata_url=f'https://{AUTH0_DOMAIN}/.well-known/openid-configuration'
)

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

@auth_bp.route("/login")
def login():
    callback_url = url_for('auth.callback', _external=True)
    return oauth.auth0.authorize_redirect(
        redirect_uri=callback_url,
        audience=f'https://{AUTH0_DOMAIN}/userinfo'
    )

@auth_bp.route("/callback", methods=["GET", "POST"])
def callback():
    try:
        token = oauth.auth0.authorize_access_token()
        session["user"] = token
        return redirect("/")
    except Exception as e:
        print(f"Auth0 callback error: {str(e)}")  # Log the error
        session.clear()  # Clear any partial session data
        return f"Error during authentication: {str(e)}", 400  # Return error to user instead of redirecting

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(
        "https://" + AUTH0_DOMAIN
        + "/v2/logout?"
        + urlencode(
            {
                "returnTo": url_for("main.index", _external=True),
                "client_id": AUTH0_CLIENT_ID,
            },
            quote_via=lambda s, *_: s,
        )
    )
