# Working Demo

Evidence that the pipeline runs and produces the committed deliverables
(SPEC §10, "working demo").

[`terminal_output.txt`](terminal_output.txt) is the verbatim output of the three
commands below, captured from a live run against the committed dataset. Each is
reproducible in seconds and needs **no API keys and no quota**, so a reviewer can
re-run them directly:

```bash
python -m unittest discover -s tests -v      # 19 offline tests
python main.py --stage send --mode simulate  # Stage 5 + duplicate prevention
python main.py --stage export                # SPEC 7-B dataset rebuild
```

## What the output demonstrates

| Evidence | Where to look |
|---|---|
| 19 unit tests pass with zero setup | section 1, `Ran 19 tests ... OK` |
| One tracker row per influencer (69) | section 2, `Tracker rows (1/influencer): 69` |
| **Duplicate prevention actually works** | section 2, `Duplicates prevented: 23` |
| Missing emails are skipped, never faked | section 2, `Skipped - no email found: 32` |
| Instagram DMs queued for manual send, never auto-sent | section 2, `Instagram DMs queued: 49` |
| Dataset exceeds the 50-influencer minimum | section 3, `Influencers: 69` |
| Unverifiable emails marked `Not Found` | section 3, `Marked 'Not Found': 32` |

### On the duplicate-prevention numbers

Section 2 shows **14 `SIMULATED_SUCCESS` and 23 `DUPLICATE_PREVENTED`**, totalling
the 37 influencers with a verified email. That split is the point: those 23 were
successfully contacted on an earlier run, so this run refused to re-contact them
and recorded why (`Already contacted on ...`). The tracker is upserted by
`channel_id`, so it stays at exactly 69 rows no matter how often the stage runs.

Stages 1–4 are not re-run here because they consume YouTube quota and Gemini's
20-requests-per-day-per-model free tier; their output is committed under `data/`.
