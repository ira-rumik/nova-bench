"""Hand-built listener outputs with known verdicts, for the rules in METHODOLOGY.md.   python -m unittest discover -s tests -v"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evaluation import align as A

REF = "the printer has done that again, and nobody knows why"  # 10 words


def item(i, twm, nvv):
    return {"id": f"en_{i}", "audio": f"/fake/en_{i}.wav", "text": REF, "text_with_mark": twm, "nvv": nvv, "system": "t", "run": "r1", "gen_ok": True}


# (request, listener transcript, expected 3-class verdict, expected 3-class unrequested sounds, expected 2-class verdict)
CASES = [
    ("<laugh> " + REF, "<laugh> " + REF, "rendered", [], "rendered"),
    ("<laugh> " + REF, REF, "not_rendered", [], "not_rendered"),
    (REF.replace("again,", "again, <sigh>"), REF.replace("again,", "again, <sigh>"), "rendered", [], "rendered"),
    (REF.replace("again,", "again, <sigh>"), REF.replace("again,", "again <sigh>,"), "rendered", [], "rendered"),          # punctuation on either side: same position
    (REF.replace("again,", "again, <sigh>"), REF.replace("again,", "again, <laugh>"), "wrong_class", [], "wrong_class"),
    (REF.replace("again,", "again, <laugh>"), REF.replace("again,", "again, <chuckle>"), "wrong_class", [], "rendered"),   # laugh/chuckle fold in the laughter view
    (REF.replace("again,", "again, <chuckle>"), REF.replace("and nobody", "and <chuckle> nobody"), "misplaced", [], "misplaced"),  # one word late = misplaced
    (REF.replace("again,", "again, <chuckle>"), REF.replace("knows why", "knows <chuckle> why"), "misplaced", [], "misplaced"),
    (REF + " <sigh>", "the printer has done that again and nobody knows why <sigh>", "rendered", [], "rendered"),          # transcript drops a comma
    ("<laugh> " + REF, "<laugh> the printer done that again, and nobody knows why", "rendered", [], "rendered"),            # transcript drops a word after the tag
    (REF.replace("again,", "again, <sigh>"), "the printer has done that has again, <sigh> and nobody knows why", "rendered", [], "rendered"),  # transcript adds a word before the tag
    ("<laugh> " + REF, "<laugh> " + REF.replace("knows why", "knows <sigh> why"), "rendered", ["sigh"], "rendered"),        # extra tag = unrequested sound
    (REF.replace("again,", "again, <laugh>"), REF.replace("again,", "again, <sigh>").replace("knows why", "knows <laugh> why"), "wrong_class", ["laugh"], "wrong_class"),  # other class AT the word wins the slot
    ("<laugh> " + REF, "<laugh> <laugh> " + REF, "rendered", ["laugh"], "rendered"),                                        # duplicate tag = one render + one unrequested
    (REF.replace("again,", "again, <laugh>"), "alpha beta gamma delta epsilon zeta eta theta iota kappa <laugh>", "not_rendered", [], "not_rendered"),  # nothing spoken: invalid
    (REF.replace("again,", "again, <laugh>"), "", "not_rendered", [], "not_rendered"),
]


class TestVerdicts(unittest.TestCase):
    def setUp(self):
        man, hyps = [], []
        for i, c in enumerate(CASES):
            man.append(item(i, c[0], A.TAGRE.search(c[0]).group(1))); hyps.append(c[1])
        man.append(item(99, "<laugh> " + REF, "laugh")); hyps.append(None)          # listener error
        self.recs = A.score(man, hyps, "test")

    def test_cases(self):
        for rec, c in zip(self.recs, CASES):
            with self.subTest(transcript=c[1][:60]):
                self.assertEqual((rec["verdict_3class"], rec["spurious_3class"], rec["verdict_2class"]), (c[2], c[3], c[4]))

    def test_listener_error_is_not_a_verdict(self):
        err = self.recs[len(CASES)]
        self.assertTrue(err["listener_error"]); self.assertNotIn("verdict_3class", err)

    def test_positions_are_in_requested_words(self):
        ref = "the printer has done that again <laugh> and nobody knows why"
        hyp = "the printer done that again <chuckle> and nobody knows why <sigh>"
        rt, ht, n = A.analyse_clip(ref, hyp)
        self.assertEqual((rt[0]["index"], ht[0]["index"], ht[1]["index"], n), (6, 6, 10, 10))

    def test_summary(self):
        rep = A.summarize(self.recs, "3class")
        self.assertEqual(rep["n_listener_errors"], 1)
        self.assertEqual(rep["classes"]["laugh"]["requested"], 9)


if __name__ == "__main__":
    unittest.main()
