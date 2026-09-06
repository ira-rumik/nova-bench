#!/usr/bin/env python3
"""Turn listener outputs into per-recording verdicts for one run.

  python score.py --run runs/my_tts/r1

For every <run>/judgments/<listener>.raw.json present (scribe_v2, gemini_verifier) writes <run>/judgments/<listener>.jsonl in
the same schema as benchmark/judgments/, and prints the per-class summary. Rules: METHODOLOGY.md / evaluation/align.py.
"""
import os, sys, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluation import align as A
from evaluation import listeners as L

ORDER = ["id", "system", "run", "listener", "nvv", "gt_index", "n_words", "coverage", "valid", "listener_error", "hyp", "hyp_tags",
         "pred_class", "pred_index", "confidence", "verdict_3class", "verdict_2class", "spurious_3class", "spurious_2class"]


def tidy(rec, listener):
    rec = dict(rec); rec["listener"] = listener; rec.pop("instrument", None); rec.pop("set", None); rec.pop("lang", None); rec.pop("gen_failed", None); rec.pop("hyp_tags_raw", None)
    return {k: rec[k] for k in ORDER if k in rec} | {k: v for k, v in rec.items() if k not in ORDER}


def summarize_print(records, name):
    for view in ("2class", "3class"):
        rep = A.summarize(records, view)
        print(f"  {name} [{view}]  listener errors {rep['n_listener_errors']}")
        for c, d in rep["classes"].items():
            if d["requested"]:
                print(f"    {c:9s} requested {d['requested']:3d}  rendered {d['rendered']:.3f}  misplaced {d['misplaced']:.3f}  wrong class {d['wrong_class']:.3f}  not rendered {d['not_rendered']:.3f}")
        if view == "2class":
            n = sum(1 for x in records if not x.get("listener_error"))
            k = sum(1 for x in records if not x.get("listener_error") and x["spurious_2class"])
            print(f"    recordings with an unrequested sound: {k}/{n} = {100 * k / max(n, 1):.1f} %")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    man = [json.loads(l) for l in open(os.path.join(a.run, "manifest.jsonl"))]
    jd = os.path.join(a.run, "judgments"); done = 0
    # Scribe v2: transcripts with tags -> the alignment scorer
    p = os.path.join(jd, "scribe_v2.raw.json")
    if os.path.exists(p):
        raw = json.load(open(p))
        for v in raw.values():
            if "words" in v:
                v["hyp"] = L.rebuild(v["words"])
        hyps = ["" if not r.get("audio") else (None if "error" in raw.get(r["id"], {"error": 1}) else raw[r["id"]].get("hyp", "")) for r in man]
        recs = [tidy(x, "scribe_v2") for x in A.score(man, hyps, "scribe_v2")]
        with open(os.path.join(jd, "scribe_v2.jsonl"), "w") as f:
            for x in recs:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        summarize_print(recs, "scribe_v2"); done += 1
    # Gemini verifier: present/position/hallucinations -> the same verdict rules
    p = os.path.join(jd, "gemini_verifier.raw.json")
    if os.path.exists(p):
        raw = json.load(open(p))
        recs = [tidy(L.gemini_record(r, raw.get(r["id"]), A.verdict, A.fold), "gemini_verifier") for r in man]
        with open(os.path.join(jd, "gemini_verifier.jsonl"), "w") as f:
            for x in recs:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        summarize_print(recs, "gemini_verifier"); done += 1
    if not done:
        sys.exit(f"no listener outputs in {jd}; run judge.py first")


if __name__ == "__main__":
    main()
