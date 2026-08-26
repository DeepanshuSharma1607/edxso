"""
main.py — Unified CLI Pipeline Runner
=====================================
Automated Micro-Influencer Outreach System (EDXSO AI Engineer Intern Assignment)

Usage:
  python main.py --stage all
  python main.py --stage discover [--refresh]
  python main.py --stage filter
  python main.py --stage enrich
  python main.py --stage personalize [--force]
  python main.py --stage send [--mode simulate|live]
  python main.py --stage export

Notes:
  --refresh  re-hydrates the channel records already in data/raw_channels.csv
             from channels.list instead of running fresh search.list queries.
             ~2 quota units per channel versus 100 per search — use this when
             you only need updated stats/descriptions, not new channels.
  --force    ignores the personalization cache and regenerates every message.
"""

import argparse
import io
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows consoles default to cp1252, which cannot encode the emoji and
# Devanagari characters present in real channel names/descriptions. Without
# this, printing a progress line raises UnicodeEncodeError and kills the run.
if sys.platform == "win32":
    for _stream in ("stdout", "stderr"):
        _s = getattr(sys, _stream)
        if hasattr(_s, "buffer"):
            setattr(sys, _stream, io.TextIOWrapper(
                _s.buffer, encoding="utf-8", errors="replace", line_buffering=True))

from ass_1.src.discovery.discover import run_discovery
from ass_1.src.filtering.filter import run_filter
from ass_1.src.enrichment.enrich import run_enrich
from ass_1.src.personalization.personalize import run_personalize
from ass_1.src.sending.send import process_outreach
from ass_1.src.utils.export_dataset import export_dataset


def main():
    parser = argparse.ArgumentParser(
        description="Automated Micro-Influencer Outreach Pipeline",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--stage",
        choices=["all", "discover", "filter", "enrich", "personalize", "send", "export"],
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
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Stage 1: re-hydrate existing channels cheaply instead of\n"
             "running new search queries (~2 units/channel vs 100/search)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Stage 4: ignore the message cache and regenerate every message",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("*** AUTOMATED MICRO-INFLUENCER OUTREACH SYSTEM ***")
    print(f"Target Stage: {args.stage.upper()}")
    print("=" * 60 + "\n")

    if args.stage in ("all", "discover"):
        print("\n--- Running Stage 1: Discovery ---")
        run_discovery(refresh_only=args.refresh)

    if args.stage in ("all", "filter"):
        print("\n--- Running Stage 2: Filtering & Classification ---")
        run_filter()

    if args.stage in ("all", "enrich"):
        print("\n--- Running Stage 3: Profile Enrichment ---")
        run_enrich()

    if args.stage in ("all", "personalize"):
        print("\n--- Running Stage 4: AI Message Personalization ---")
        run_personalize(force=args.force)

    if args.stage in ("all", "send"):
        print("\n--- Running Stage 5: Sending Layer & Outreach Tracker ---")
        process_outreach(mode=args.mode)

    # Runs last: it joins Stage 2's verdict, Stage 3's profiles and Stage 5's
    # outreach status into the single flat dataset SPEC 7-B asks for.
    if args.stage in ("all", "export"):
        print("\n--- Export: SPEC 7-B influencer dataset ---")
        export_dataset()

    print("\n" + "=" * 60)
    print("[+] PIPELINE EXECUTION FINISHED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
