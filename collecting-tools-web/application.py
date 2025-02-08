from app import create_app
import os

application = create_app()  # Elastic Beanstalk looks for 'application' by default

# Set Flask environment variables
os.environ['FLASK_APP'] = 'application'

if __name__ == '__main__':
    application.run(host='0.0.0.0', port=8080)
