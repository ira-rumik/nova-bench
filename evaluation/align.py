"""NoVA scoring: normalisation, tag-aware alignment, per-request verdicts, per-run summary.

Positions are counted in WORDS of the requested text (punctuation stripped, lower-cased). Each requested tag gets one verdict:
    rendered      the requested class at the requested word
    wrong_class   another class at the requested word (laugh and chuckle fold together in the laughter view)
    misplaced     the requested class somewhere else in the recording
    not_rendered  nothing of the requested class anywhere (includes recordings with no speech)
Every listener tag not used by the verdict is an UNREQUESTED SOUND. A recording in which fewer than half of the requested words
were spoken is invalid: its tags are discarded and the request is not_rendered.

Transcript and request are tokenised with tags kept as tokens and Levenshtein-aligned (tags never pair with words; a tag
insert/delete is cheaper than a word insert/delete); each listener tag is placed in requested-word coordinates = number of
requested words consumed before it, so transcription errors do not move positions. See METHODOLOGY.md.
"""
import re, collections, difflib
import numpy as np

TAGS  = ["laugh", "chuckle", "sigh"]
TAGRE = re.compile(r"<(laugh|chuckle|sigh)>")
SPLIT = re.compile(r"(<(?:laugh|chuckle|sigh)>)")
MIN_COVERAGE = 0.5      # share of requested words that must have been spoken for the clip to count
NEAR = 0.8              # difflib ratio at which a transcribed word counts as the requested word (forty/40 style variants excepted)

def fold(c, view):
    return c if view == "3class" else ("laughter" if c in ("laugh", "chuckle") else "sigh")

def classes(view): return TAGS if view == "3class" else ["laughter", "sigh"]

def norm_word(t):
    w = re.sub(r"[^\w]", "", t.lower())
    return w if re.search(r"\w", w) else None          # punctuation-only tokens are not words

def toks(text):
    """Tags as '<cls>' tokens, words normalised, punctuation-only tokens dropped."""
    out = []
    for t in str(text).split():
        for p in SPLIT.split(t):
            if not p: continue
            if TAGRE.fullmatch(p): out.append(p)
            else:
                w = norm_word(p)
                if w: out.append(w)
    return out

# Levenshtein with tag-aware costs: word ins/del 1.0, tag ins/del 0.9 (a displaced tag is re-inserted
# rather than pairing with the word it displaced), sub word<->word 1.0, tag<->tag 0.9, tag<->word 3.0.
def _indel(x): return 0.9 if TAGRE.fullmatch(x) else 1.0
def _sub(x, y):
    if x == y: return 0.0
    tx, ty = bool(TAGRE.fullmatch(x)), bool(TAGRE.fullmatch(y))
    return (0.9 if tx else 1.0) if tx == ty else 3.0

def align(a, b, sub=_sub, indel=_indel):
    n, m = len(a), len(b); EPS = 1e-9
    D = np.zeros((n + 1, m + 1))
    for i in range(1, n + 1): D[i, 0] = D[i - 1, 0] + indel(a[i - 1])
    for j in range(1, m + 1): D[0, j] = D[0, j - 1] + indel(b[j - 1])
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i, j] = min(D[i - 1, j] + indel(a[i - 1]), D[i, j - 1] + indel(b[j - 1]), D[i - 1, j - 1] + sub(a[i - 1], b[j - 1]))
    ops, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and abs(D[i, j] - (D[i - 1, j - 1] + sub(a[i - 1], b[j - 1]))) < EPS:
            ops.append(("match" if a[i - 1] == b[j - 1] else "sub", i - 1, j - 1)); i, j = i - 1, j - 1
        elif i > 0 and abs(D[i, j] - (D[i - 1, j] + indel(a[i - 1]))) < EPS: ops.append(("del", i - 1, None)); i -= 1
        else: ops.append(("ins", None, j - 1)); j -= 1
    return ops[::-1]

def tagcls(t):
    m = TAGRE.fullmatch(t) if t else None
    return m.group(1) if m else None

def analyse_clip(ref_twm, hyp):
    """-> ref_tags [{cls,index}], hyp_tags [{cls,index}], L (reference words); index = words before the tag."""
    A, B = toks(ref_twm), toks(hyp)
    words, ref_tags, hyp_tags = 0, [], []
    for op, i, j in align(A, B):
        ac = tagcls(A[i]) if i is not None else None
        bc = tagcls(B[j]) if j is not None else None
        if ac: ref_tags.append({"cls": ac, "index": words})
        if bc: hyp_tags.append({"cls": bc, "index": words})
        if i is not None and not ac: words += 1
    return ref_tags, hyp_tags, words

def coverage(ref_text, hyp):
    """Share of requested words actually spoken: a word counts only if the aligned transcript word is the
    same word or a near-spelling (ratio >= NEAR). Substituting unrelated words does not count."""
    rw = [w for w in (norm_word(t) for t in str(ref_text).split()) if w]
    hw = [w for w in (norm_word(t) for t in TAGRE.sub(" ", str(hyp)).split()) if w]
    if not rw: return None
    def sub(x, y): return 0.0 if x == y else (0.5 if difflib.SequenceMatcher(None, x, y).ratio() >= NEAR else 1.0)
    spoken = 0
    for op, i, j in align(rw, hw, sub=sub, indel=lambda x: 1.0):
        if op == "match" or (op == "sub" and difflib.SequenceMatcher(None, rw[i], hw[j]).ratio() >= NEAR): spoken += 1
    return spoken / len(rw)

def verdict(req_cls, gt_index, hyp_tags, view, valid=True):
    """One label for the request + the list of leftover (spurious) tag classes, in the given view."""
    if req_cls is None:                                          # clean control: everything is spurious
        return None, [fold(h["cls"], view) for h in hyp_tags]
    if not valid:
        return "not_rendered", []
    req = fold(req_cls, view); rest = list(hyp_tags)
    at_same = [h for h in rest if h["index"] == gt_index and fold(h["cls"], view) == req]
    if at_same:
        rest.remove(at_same[0]); return "rendered", [fold(h["cls"], view) for h in rest]
    at_other = [h for h in rest if h["index"] == gt_index]
    if at_other:
        rest.remove(at_other[0]); return "wrong_class", [fold(h["cls"], view) for h in rest]
    same = sorted((h for h in rest if fold(h["cls"], view) == req), key=lambda h: abs(h["index"] - gt_index))
    if same:
        rest.remove(same[0]); return "misplaced", [fold(h["cls"], view) for h in rest]
    return "not_rendered", [fold(h["cls"], view) for h in rest]

def score(man, hyps, name="I1"):
    records = []
    for r, hyp in zip(man, hyps):
        req = r.get("nvv") if r.get("nvv") in TAGS else None
        rec = {"id": r["id"], "system": r.get("system"), "lang": r.get("lang"), "run": r.get("run"), "set": r.get("set"),
               "nvv": req, "instrument": name, "listener_error": False, "gen_failed": False}
        if r.get("gen_ok") is False or not r.get("audio"):       # the SYSTEM produced nothing: the request was not rendered
            rec.update({"gen_failed": True, "gt_index": None, "n_words": None, "coverage": 0.0, "valid": False, "hyp": "",
                        "hyp_tags": [], "hyp_tags_raw": [], "pred_class": None, "pred_index": None})
            for view in ("3class", "2class"):
                rec[f"verdict_{view}"] = "not_rendered" if req else None; rec[f"spurious_{view}"] = []
            records.append(rec); continue
        if hyp is None:                                          # the LISTENER failed on this recording: missing data, not a verdict
            rec["listener_error"] = True; records.append(rec); continue
        ref_tags, hyp_tags, L = analyse_clip(r["text_with_mark"], hyp)
        assert len(ref_tags) <= 1, f"{r['id']}: one tag per item expected, found {len(ref_tags)}"
        gt = ref_tags[0]["index"] if ref_tags else None
        cov = coverage(r["text"], hyp)
        valid = cov is None or cov >= MIN_COVERAGE
        rec.update({"gt_index": gt, "n_words": L, "coverage": cov, "valid": valid, "hyp": hyp,
                    "hyp_tags": hyp_tags if valid else [], "hyp_tags_raw": hyp_tags})
        for view in ("3class", "2class"):
            v, sp = verdict(req, gt, hyp_tags if valid else [], view, valid)
            rec[f"verdict_{view}"] = v; rec[f"spurious_{view}"] = sp
        same = [h for h in hyp_tags if valid and req and fold(h["cls"], "3class") == req]
        at = [h for h in hyp_tags if valid and gt is not None and h["index"] == gt]
        rec["pred_class"] = (at[0]["cls"] if at else (same[0]["cls"] if same else None))
        rec["pred_index"] = (at[0]["index"] if at else (same[0]["index"] if same else None))
        records.append(rec)
    return records

def summarize(records, view):
    rs = [x for x in records if not x.get("listener_error")]
    tagged = [x for x in rs if x["nvv"]]; clean = [x for x in rs if not x["nvv"]]
    out = {"view": view, "n_clips": len(records), "n_scored": len(rs), "n_listener_errors": len(records) - len(rs),
           "n_gen_failed": sum(1 for x in rs if x.get("gen_failed")), "n_tagged": len(tagged), "n_clean": len(clean), "classes": {}}
    for c in classes(view):
        rows = [x for x in tagged if fold(x["nvv"], view) == c]
        n = len(rows); cnt = collections.Counter(x[f"verdict_{view}"] for x in rows)
        out["classes"][c] = {"requested": n, **{k: (cnt[k] / n if n else None) for k in ("rendered", "misplaced", "wrong_class", "not_rendered")},
                             "invalid": (sum(not x["valid"] for x in rows) / n if n else None)}
    sp_t = collections.Counter(s for x in tagged for s in x[f"spurious_{view}"])
    sp_c = collections.Counter(s for x in clean for s in x[f"spurious_{view}"])
    out["spurious_per_100"] = {"tagged": (100 * sum(sp_t.values()) / len(tagged) if tagged else None),
                               "clean": (100 * sum(sp_c.values()) / len(clean) if clean else None),
                               "tagged_by_class": dict(sp_t), "clean_by_class": dict(sp_c)}
    out["invalid_rate"] = (sum(not x["valid"] for x in rs) / len(rs) if rs else None)
    out["coverage_mean"] = float(np.mean([x["coverage"] for x in rs if x["coverage"] is not None])) if rs else None
    return out

