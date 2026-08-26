import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ass_1.src.filtering.filter import run_filter

if __name__ == "__main__":
    run_filter()
