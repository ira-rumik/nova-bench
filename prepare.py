#!/usr/bin/env python3
"""Register recordings of a system for evaluation.

  python prepare.py --system my_tts --runs runs/my_tts [--dry-run]

Expects runs/my_tts/r1, r2, r3 (any number of run folders), each holding one <id>.wav per prompt in
benchmark/prompts.jsonl (ids en_<n>): mono PCM16 WAV. Writes <run>/manifest.jsonl with one row per prompt. A prompt with
no recording gets a row with gen_ok=false; the scorer counts it as not rendered so denominators never shrink.
--dry-run validates coverage and audio format and writes nothing.
"""
import os, sys, json, glob, argparse
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(HERE, "benchmark", "prompts.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True, help="system id used in manifests and tables, e.g. my_tts")
    ap.add_argument("--runs", required=True, help="folder holding one sub-folder per synthesis run (r1, r2, ...)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    prompts = [json.loads(l) for l in open(PROMPTS)]
    run_dirs = sorted(d for d in glob.glob(os.path.join(a.runs, "*")) if os.path.isdir(d) and glob.glob(os.path.join(d, "*.wav")))
    if not run_dirs:
        sys.exit(f"no run folders with .wav files under {a.runs}")
    problems = 0
    for rd in run_dirs:
        run = os.path.basename(rd); rows = []; missing = []; bad = []
        for p in prompts:
            wav = os.path.join(rd, f"{p['id']}.wav")
            row = {"id": p["id"], "system": a.system, "run": run, "nvv": p["nvv"], "text": p["text"], "text_with_mark": p["text_with_mark"]}
            if not os.path.exists(wav):
                missing.append(p["id"]); row.update({"audio": None, "gen_ok": False}); rows.append(row); continue
            info = sf.info(wav)
            if info.channels != 1 or "PCM_16" not in info.subtype:
                bad.append(f"{p['id']}: {info.channels} ch, {info.subtype}")
            row.update({"audio": os.path.abspath(wav), "gen_ok": True, "dur": round(info.duration, 2), "sr": info.samplerate}); rows.append(row)
        print(f"{a.system}/{run}: {len(prompts) - len(missing)}/{len(prompts)} recordings" + (f"; MISSING {len(missing)}: {missing[:8]}" if missing else "") + (f"; BAD FORMAT {len(bad)}: {bad[:4]}" if bad else ""))
        problems += len(bad)
        if not a.dry_run:
            with open(os.path.join(rd, "manifest.jsonl"), "w") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"  wrote {os.path.join(rd, 'manifest.jsonl')}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
