"""
main.py — Unified CLI Pipeline Runner
=====================================
Automated Micro-Influencer Outreach System (EDXSO AI Engineer Intern Assignment)

Usage:
  python main.py --stage all
  python main.py --stage discover
  python main.py --stage filter
  python main.py --stage enrich
  python main.py --stage personalize
  python main.py --stage send [--mode simulate|live]
"""

import argparse
import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ass_1.src.discovery.discover import run_discovery
from ass_1.src.filtering.filter import run_filter
from ass_1.src.enrichment.enrich import run_enrich
from ass_1.src.personalization.personalize import run_personalize
from ass_1.src.sending.send import process_outreach


def main():
    parser = argparse.ArgumentParser(
        description="Automated Micro-Influencer Outreach Pipeline",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--stage",
        choices=["all", "discover", "filter", "enrich", "personalize", "send"],
        default="all",
        help=(
            "Pipeline stage to execute:\n"
            "  all         - Run all 5 stages end-to-end\n"
            "  discover    - Stage 1: YouTube API discovery\n"
            "  filter      - Stage 2: Multi-factor scoring & filtering\n"
            "  enrich      - Stage 3: Profile enrichment (themes, emails)\n"
            "  personalize - Stage 4: AI personalized pitches (Gemini)\n"
            "  send        - Stage 5: Outreach sending & duplicate tracking\n"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["simulate", "live"],
        default="simulate",
        help="Sending mode for Stage 5 (default: simulate)",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("*** AUTOMATED MICRO-INFLUENCER OUTREACH SYSTEM ***")
    print(f"Target Stage: {args.stage.upper()}")
    print("=" * 60 + "\n")

    if args.stage in ("all", "discover"):
        print("\n--- Running Stage 1: Discovery ---")
        run_discovery()

    if args.stage in ("all", "filter"):
        print("\n--- Running Stage 2: Filtering & Classification ---")
        run_filter()

    if args.stage in ("all", "enrich"):
        print("\n--- Running Stage 3: Profile Enrichment ---")
        run_enrich()

    if args.stage in ("all", "personalize"):
        print("\n--- Running Stage 4: AI Message Personalization ---")
        run_personalize()

    if args.stage in ("all", "send"):
        print("\n--- Running Stage 5: Sending Layer & Outreach Tracker ---")
        process_outreach(mode=args.mode)

    print("\n" + "=" * 60)
    print("[+] PIPELINE EXECUTION FINISHED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
