import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ass_1.src.enrichment.enrich import run_enrich

if __name__ == "__main__":
    run_enrich()
