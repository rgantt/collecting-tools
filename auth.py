from functools import wraps
from flask import Blueprint, redirect, session, url_for, current_app, request
from authlib.integrations.flask_client import OAuth
from urllib.parse import urlencode
import json
from auth_config import (
    AUTH0_CLIENT_ID,
    AUTH0_CLIENT_SECRET,
    AUTH0_DOMAIN,
    AUTH0_CALLBACK_URL
)

auth_bp = Blueprint('auth', __name__)
oauth = OAuth()

auth0 = oauth.register(
    'auth0',
    client_id=AUTH0_CLIENT_ID,
    client_secret=AUTH0_CLIENT_SECRET,
    api_base_url=f'https://{AUTH0_DOMAIN}',
    access_token_url=f'https://{AUTH0_DOMAIN}/oauth/token',
    authorize_url=f'https://{AUTH0_DOMAIN}/authorize',
    server_metadata_url=f'https://{AUTH0_DOMAIN}/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid profile email',
    },
)

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

@auth_bp.route('/login')
def login():
    return auth0.authorize_redirect(
        redirect_uri=AUTH0_CALLBACK_URL,
        audience=f'https://{AUTH0_DOMAIN}/userinfo'
    )

@auth_bp.route('/callback')
def callback():
    try:
        token = auth0.authorize_access_token()
        resp = auth0.get('userinfo')
        userinfo = resp.json()
        session['user'] = {
            'user_id': userinfo['sub'],
            'name': userinfo.get('name', ''),
            'email': userinfo.get('email', '')
        }
        return redirect('/')
    except Exception as e:
        print(f"Auth0 callback error: {str(e)}")
        return redirect('/login')

@auth_bp.route('/logout')
def logout():
    session.clear()
    params = {
        'returnTo': url_for('index', _external=True),
        'client_id': AUTH0_CLIENT_ID
    }
    return redirect(auth0.api_base_url + '/v2/logout?' + urlencode(params))
