import os
import sys
import tempfile

# Every test run gets its own empty data folder; the app modules read it at import time.
os.environ['FRAME_PLAN_DATA'] = tempfile.mkdtemp(prefix='frame-plan-test-')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
