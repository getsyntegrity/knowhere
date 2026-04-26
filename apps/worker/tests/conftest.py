"""
Pytest configuration for worker tests.

Sets up the Python path to include the app and shared packages.
"""

import sys
from pathlib import Path

# Add the worker app directory to the Python path
worker_dir = Path(__file__).parent.parent
sys.path.insert(0, str(worker_dir))

# Add the worker test support package to the Python path
tests_dir = Path(__file__).parent
sys.path.insert(0, str(tests_dir))

# Add the shared-python package to the Python path
shared_dir = worker_dir.parent.parent / "packages" / "shared-python"
sys.path.insert(0, str(shared_dir))
