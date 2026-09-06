#!/usr/bin/env python3
"""Tables from per-recording judgments.

  python aggregate.py --check                       # rebuild the published tables from benchmark/judgments and compare with benchmark/results
  python aggregate.py --runs runs/my_tts/r1 runs/my_tts/r2 runs/my_tts/r3 [--name "My TTS"]
                                                    # score a new system from its judgments (listeners present) beside the published rows

Rates are the fraction of requests rendered at the requested word, averaged over runs; laughter-union = a laugh or a chuckle
accepted for either request. S(listener) = (laughter-union + sigh) / 2 with an absent class counting 0; Score = mean of S over
listeners. Ties break on the smaller share of recordings with an unrequested sound. See METHODOLOGY.md.
"""
import os, sys, csv, json, glob, argparse, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
JUD = os.path.join(HERE, "benchmark", "judgments"); RES = os.path.join(HERE, "benchmark", "results")
LISTENERS = [("silk_asr", "silk-ASR (ours)"), ("gemini_verifier", "Gemini verifier"), ("scribe_v2", "Scribe v2")]
NAMES = {"grok": "Grok (ara)", "inworld_tts2": "Inworld TTS-2 (Ashley)", "rumik_oss_1": "Rumik-OSS 1 (Ira)", "orpheus_3b": "Orpheus 3B (tara)",
         "elevenlabs_v3": "ElevenLabs v3 (Jessica)", "gemini_3_1_flash_tts": "Gemini 3.1 Flash TTS (Kore)", "cartesia_sonic_3_6": "Cartesia Sonic 3.6 (Monica)"}
TAGS = {"cartesia_sonic_3_6": "L"}


def fold(c): return "laughter" if c in ("laugh", "chuckle") else c


def load_system(run_dirs, listener):
    """-> {run: [records]} for one listener, or {} if that listener has no file in any run."""
    out = {}
    for rd in run_dirs:
        p = os.path.join(rd, f"{listener}.jsonl")
        if os.path.exists(p):
            out[os.path.basename(rd)] = [json.loads(l) for l in open(p)]
    return out


def rates(by_run):
    """Per-run rates averaged: rendered per class (2-class and 3-class) and share of recordings with an unrequested sound."""
    r2, r3, sp = {}, {}, []
    for run, R in by_run.items():
        R = [x for x in R if not x.get("listener_error")]
        for c in ("laughter", "sigh"):
            rows = [x for x in R if x["nvv"] and fold(x["nvv"]) == c]
            if rows:
                r2.setdefault(c, []).append(sum(x["verdict_2class"] == "rendered" for x in rows) / len(rows))
        for c in ("laugh", "chuckle", "sigh"):
            rows = [x for x in R if x["nvv"] == c]
            if rows:
                r3.setdefault(c, []).append(sum(x["verdict_3class"] == "rendered" for x in rows) / len(rows))
        sp.append(100 * sum(1 for x in R if x["spurious_2class"]) / len(R))
    return {c: st.mean(v) for c, v in r2.items()}, {c: st.mean(v) for c, v in r3.items()}, st.mean(sp)


def system_row(system, run_dirs, tags=None):
    row = {"system": system, "tags": tags or "L·C·S", "listeners": {}}
    for lid, _ in LISTENERS:
        by_run = load_system(run_dirs, lid)
        if not by_run:
            continue
        r2, r3, sp = rates(by_run)
        S = ((r2.get("laughter") or 0) + (r2.get("sigh") or 0)) / 2
        row["listeners"][lid] = {"laughter": r2.get("laughter"), "sigh": r2.get("sigh"), "laugh": r3.get("laugh"), "chuckle": r3.get("chuckle"), "sigh3": r3.get("sigh"), "unrequested": sp, "S": S}
    ls = row["listeners"]
    row["score"] = st.mean(v["S"] for v in ls.values()) if ls else None
    row["unrequested_silk"] = ls.get("silk_asr", {}).get("unrequested")
    return row


def published_rows():
    rows = []
    for s in sorted(os.listdir(JUD)):
        run_dirs = sorted(glob.glob(os.path.join(JUD, s, "r*")))
        rows.append(system_row(s, run_dirs, TAGS.get(s)))
    return sorted(rows, key=lambda r: (-r["score"], r["unrequested_silk"] or 0))


def f2(v): return "n/a" if v is None else f"{v:.2f}"


def tables(rows):
    t1 = [["system", "tags"] + [f"{n} {c}" for _, n in LISTENERS for c in ("laughter-union", "sigh")] + ["score"]]
    t2 = [["system"] + [n for _, n in LISTENERS]]
    ta = [["system"] + [f"{n} {c}" for _, n in LISTENERS for c in ("laugh", "chuckle", "sigh")]]
    for r in rows:
        name = NAMES.get(r["system"], r["system"]); L = r["listeners"]
        t1.append([name, r["tags"]] + [f2(L.get(l, {}).get(c)) for l, _ in LISTENERS for c in ("laughter", "sigh")] + [f2(r["score"])])
        t2.append([name] + [("n/a" if l not in L else f"{L[l]['unrequested']:.1f} %") for l, _ in LISTENERS])
        ta.append([name] + [("n/a" if (l not in L or L[l].get(c) is None or (c == "chuckle" and r["tags"] == "L")) else f"{L[l][c]:.2f}") for l, _ in LISTENERS for c in ("laugh", "chuckle", "sigh3")])
    return {"table1_rendered": t1, "table2_unrequested_sounds": t2, "appendix_split": ta}


def print_table(t):
    w = [max(len(str(r[i])) for r in t) for i in range(len(t[0]))]
    for k, r in enumerate(t):
        print("  " + "  ".join(str(v).ljust(w[i]) if i == 0 else str(v).rjust(w[i]) for i, v in enumerate(r)))
        if k == 0:
            print("  " + "  ".join("-" * x for x in w))


def tex_tables(rows):
    tx = lambda x: x.replace("&", r"\&").replace("%", r"\%").replace("n/a", "--")
    D = [n for _, n in LISTENERS]
    L = [r"\begin{table}[t]\centering\small\setlength{\tabcolsep}{5pt}", r"\begin{tabular}{ll|rr|rr|rr|r}", r"\toprule",
         r" & & " + " & ".join(rf"\multicolumn{{2}}{{c|}}{{{d}}}" for d in D) + r" & \\", r"\cmidrule(lr){3-4} \cmidrule(lr){5-6} \cmidrule(lr){7-8}",
         r"Model & Tags & " + " & ".join(r"laughter$\cup$ & sigh" for _ in D) + r" & Score \\", r"\midrule"]
    for r in rows:
        Ls = r["listeners"]
        L.append(tx(NAMES.get(r["system"], r["system"])) + f" & {r['tags']} & " + " & ".join(tx(f2(Ls.get(l, {}).get(c))) for l, _ in LISTENERS for c in ("laughter", "sigh")) + rf" & \textbf{{{f2(r['score'])}}} \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\caption{Fraction of requests rendered at the requested word (mean of 3 synthesis runs), per listener. laughter$\cup$ = a laugh or a chuckle accepted for either request. Tags: L laugh, C chuckle, S sigh accepted. ``--'' = no tag for that class. Score = mean over listeners of (laughter$\cup$ + sigh)/2, an absent class counting 0.}", r"\label{tab:nova_rendered}", r"\end{table}", ""]
    t1 = "\n".join(L)
    L = [r"\begin{table}[t]\centering\small", r"\begin{tabular}{l|rrr}", r"\toprule", r"Model & " + " & ".join(D) + r" \\", r"\midrule"]
    for r in rows:
        Ls = r["listeners"]; L.append(tx(NAMES.get(r["system"], r["system"])) + " & " + " & ".join(("--" if l not in Ls else f"{Ls[l]['unrequested']:.1f}\\%") for l, _ in LISTENERS) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\caption{Share of recordings containing a laugh, chuckle or sigh that was not requested, per listener (mean of 3 runs; lower is better).}", r"\label{tab:nova_unrequested}", r"\end{table}", ""]
    return {"table1_rendered": t1, "table2_unrequested_sounds": "\n".join(L)}


def write_results(T, rows):
    os.makedirs(RES, exist_ok=True)
    for name, t in T.items():
        with open(os.path.join(RES, f"{name}.csv"), "w", newline="") as f:
            csv.writer(f).writerows(t)
    for name, body in tex_tables(rows).items():
        open(os.path.join(RES, f"{name}.tex"), "w").write("% generated by aggregate.py --write; needs \\usepackage{booktabs}\n" + body)
    print("wrote", ", ".join(f"benchmark/results/{n}.csv" for n in T), "+ table1_rendered.tex, table2_unrequested_sounds.tex")


def check(T):
    bad = 0
    for name, t in T.items():
        p = os.path.join(RES, f"{name}.csv")
        ref = list(csv.reader(open(p)))
        if ref != [[str(v) for v in r] for r in t]:
            bad += 1; print(f"MISMATCH: {name}.csv")
            for a, b in zip(ref, t):
                if a != [str(v) for v in b]:
                    print("   reference:", a); print("   computed: ", b)
    n = sum(1 for _ in glob.glob(os.path.join(JUD, "*", "r*", "*.jsonl")))
    print(("PASS: " if not bad else "FAIL: ") + f"tables rebuilt from {n} judgment files in benchmark/judgments and compared with benchmark/results/*.csv")
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true", help="(maintainers) regenerate benchmark/results from benchmark/judgments")
    ap.add_argument("--runs", nargs="*", default=[], help="run folders of a new system (each with judgments/<listener>.jsonl)")
    ap.add_argument("--name", default="", help="display name for the new system")
    a = ap.parse_args()
    rows = published_rows()
    if a.runs:
        new = system_row(a.name or "candidate", [os.path.join(r, "judgments") for r in a.runs])
        if not new["listeners"]:
            sys.exit("no scored listeners found; run judge.py and score.py first")
        NAMES[new["system"]] = a.name or "candidate"
        rows = sorted(rows + [new], key=lambda r: (-(r["score"] or 0), r["unrequested_silk"] or 0))
        print(f"note: '{new['system']}' has {len(new['listeners'])} of 3 listeners; its score averages the listeners present")
    T = tables(rows)
    for name, t in T.items():
        print(f"\n{name}"); print_table(t)
    if a.write:
        write_results(T, rows)
    if a.check:
        sys.exit(0 if check(T) else 1)


if __name__ == "__main__":
    main()
