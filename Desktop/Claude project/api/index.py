import sys
import os

# Add project root to path so tools/ can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.api_server import app
