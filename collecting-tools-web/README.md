# Collecting Tools Web Application

This is the web interface for the Collecting Tools project, designed to be deployed to AWS.

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Initialize the database:
```bash
flask db upgrade
```

5. Run the development server:
```bash
flask run
```

## Deployment

This application is designed to be deployed to AWS. Deployment instructions will be added soon.

## Project Structure

```
collecting-tools-web/
├── app/
│   ├── __init__.py
│   ├── routes.py
│   ├── auth.py
│   ├── models.py
│   ├── templates/
│   └── static/
├── migrations/
├── tests/
├── config.py
├── requirements.txt
└── README.md
```
