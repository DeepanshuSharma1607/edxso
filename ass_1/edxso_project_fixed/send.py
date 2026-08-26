import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ass_1.src.sending.send import process_outreach

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 5 Sending Layer")
    parser.add_argument("--mode", choices=["simulate", "live"], default="simulate", help="Sending mode")
    args = parser.parse_args()
    process_outreach(mode=args.mode)
