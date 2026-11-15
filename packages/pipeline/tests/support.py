import importlib
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]


def import_pipeline(name):
    path = str(PIPELINE_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module(name)
