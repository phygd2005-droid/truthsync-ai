"""Loads a local .env file (if python-dotenv is installed). Import this FIRST."""
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
