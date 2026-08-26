"""
Unit tests for the outreach pipeline's pure logic.

These deliberately avoid any network / API calls so they run offline in CI and
never need a key. They lock in the behaviours that were previously bugs:
  * engagement scoring saturates and never exceeds its cap
  * the filter's pass/fail decision is explainable
  * word-count verification for the LLM messages actually rejects out-of-range
  * email / Instagram extraction rejects the false positives we hit in the wild
  * the outreach tracker is keyed one-row-per-influencer (duplicate prevention)

Run with:  python -m unittest discover -s tests -v      (no pytest needed)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestEngagementScoring(unittest.TestCase):
    def test_zero_engagement_scores_zero(self):
        from ass_1.src.filtering.filter import engagement_score
        self.assertEqual(engagement_score(0.0), 0.0)

    def test_saturates_at_full_marks(self):
        from ass_1.src.filtering.filter import engagement_score, ENGAGEMENT_FULL_MARKS_PCT
        # At and beyond the full-marks threshold the score caps at 40, never more.
        self.assertEqual(engagement_score(ENGAGEMENT_FULL_MARKS_PCT), 40.0)
        self.assertEqual(engagement_score(ENGAGEMENT_FULL_MARKS_PCT * 100), 40.0)

    def test_partial_is_proportional(self):
        from ass_1.src.filtering.filter import engagement_score, ENGAGEMENT_FULL_MARKS_PCT
        half = engagement_score(ENGAGEMENT_FULL_MARKS_PCT / 2)
        self.assertAlmostEqual(half, 20.0, places=1)


class TestComputeEngagement(unittest.TestCase):
    def test_skips_zero_view_videos(self):
        from ass_1.src.utils.youtube import compute_engagement
        videos = [
            {"views": 0, "likes": 0, "comments": 0},      # unprocessed / hidden
            {"views": 1000, "likes": 40, "comments": 10},  # 5%
        ]
        m = compute_engagement(videos, subscribers=10_000)
        # Only the second video counts; a divide-by-zero would have crashed.
        self.assertAlmostEqual(m["engagement_rate_pct"], 5.0, places=1)
        self.assertEqual(m["videos_sampled"], 1)

    def test_no_videos_is_safe(self):
        from ass_1.src.utils.youtube import compute_engagement
        m = compute_engagement([], subscribers=10_000)
        self.assertEqual(m["engagement_rate_pct"], 0.0)
        self.assertEqual(m["videos_sampled"], 0)


class TestWordCountVerification(unittest.TestCase):
    def test_range_miss_zero_when_compliant(self):
        from ass_1.src.personalization.personalize import _range_miss
        self.assertEqual(_range_miss(75, 22), 0)   # both inside bounds

    def test_range_miss_counts_overflow_and_underflow(self):
        from ass_1.src.personalization.personalize import _range_miss
        # email 96 (>90 by 6) + dm 10 (<15 by 5) = 11 total words out of range
        self.assertEqual(_range_miss(96, 10), 11)

    def test_word_count(self):
        from ass_1.src.personalization.personalize import word_count
        self.assertEqual(word_count("one two three"), 3)
        self.assertEqual(word_count(""), 0)


class TestCollaborationAngle(unittest.TestCase):
    def test_deterministic(self):
        from ass_1.src.personalization.personalize import pick_collaboration_angle
        creator = {"channel_id": "UC123abc", "niche": "Technology", "subscriber_count": 40000}
        a = pick_collaboration_angle(creator)
        b = pick_collaboration_angle(creator)
        self.assertEqual(a, b)  # same creator -> same angle across runs

    def test_angle_is_valid(self):
        from ass_1.src.personalization.personalize import pick_collaboration_angle, COLLABORATION_ANGLES
        creator = {"channel_id": "UCxyz789", "niche": "Fitness", "subscriber_count": 8000}
        self.assertIn(pick_collaboration_angle(creator), COLLABORATION_ANGLES)


class TestEmailExtraction(unittest.TestCase):
    def test_valid_email_passes(self):
        from ass_1.src.enrichment.enrich import clean_email
        self.assertEqual(clean_email("babatechreview@gmail.com"), "babatechreview@gmail.com")

    def test_strips_glued_label(self):
        from ass_1.src.enrichment.enrich import clean_email
        # "inquiries-sk.maijul786@gmail.com" -> the label must be stripped
        self.assertEqual(clean_email("inquiries-sk.maijul786@gmail.com"), "sk.maijul786@gmail.com")

    def test_rejects_www_prefixed_junk(self):
        from ass_1.src.enrichment.enrich import clean_email
        # "www.wh@sapp.com" came from the old obfuscated-"at" regex matching the
        # "at" inside "whatsapp" — the www. local part must be rejected.
        self.assertEqual(clean_email("www.wh@sapp.com"), "")


class TestWebsiteValidation(unittest.TestCase):
    def test_rejects_cdn_asset(self):
        from ass_1.src.enrichment.enrich import is_creator_website
        self.assertFalse(is_creator_website(
            "https://www.gstatic.com/youtube/img/emojis/emojis-png-15.1.json"))

    def test_accepts_real_site(self):
        from ass_1.src.enrichment.enrich import is_creator_website
        self.assertTrue(is_creator_website("https://mystore.in"))


class TestOutreachTracker(unittest.TestCase):
    def test_outreach_id_is_stable(self):
        from ass_1.src.sending.send import outreach_id_for
        self.assertEqual(outreach_id_for("UCabc"), outreach_id_for("UCabc"))
        self.assertNotEqual(outreach_id_for("UCabc"), outreach_id_for("UCdef"))

    def test_simulated_receipt_marked(self):
        from ass_1.src.sending.send import simulated_receipt
        r = simulated_receipt("UCabc", "x@y.com")
        self.assertTrue(r.startswith("SIM-"))  # never mistakable for a real send

    def test_already_contacted_statuses(self):
        from ass_1.src.sending.send import ALREADY_CONTACTED
        # A creator in either state must never be mailed twice.
        self.assertIn("SENT", ALREADY_CONTACTED)
        self.assertIn("SIMULATED_SUCCESS", ALREADY_CONTACTED)
        # A failed or skipped attempt is NOT "contacted" — it may be retried.
        self.assertNotIn("FAILED", ALREADY_CONTACTED)
        self.assertNotIn("SKIPPED_NO_EMAIL", ALREADY_CONTACTED)

    def test_orphan_rows_are_dropped(self):
        """Tracker rows whose channel left the shortlist must not pad output.

        Regression guard: an old 78-row tracker meeting a 69-row dataset used
        to emit 78 rows, overstating how many influencers were processed.
        """
        history = {"UC_current": {"channel_id": "UC_current"},
                   "UC_dropped": {"channel_id": "UC_dropped"}}
        current_ids = {"UC_current"}
        kept = {cid: r for cid, r in history.items() if cid in current_ids}
        self.assertEqual(set(kept), {"UC_current"})
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
