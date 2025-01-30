import os
import sys
import pytest

# Add the parent directory to Python path so we can import the main package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) 