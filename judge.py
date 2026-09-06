#!/usr/bin/env python3
"""Run one public listener over one synthesis run. Makes paid API calls.

  python judge.py --listener scribe --run runs/my_tts/r1                   # ELEVENLABS_API_KEY
  python judge.py --listener gemini --run runs/my_tts/r1 --vertex --project my-project   # or GEMINI_API_KEY

Reads <run>/manifest.jsonl (from prepare.py); writes <run>/judgments/<listener>.raw.json keyed by prompt id. Resumable:
a recording already judged with the same audio bytes (md5) and, for Gemini, the same model and prompt version, is skipped.
Failed calls are stored with an "error" and become listener errors in score.py, never low scores.
"""
import os, sys, json, time, argparse, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluation import listeners as L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listener", required=True, choices=["scribe", "gemini"])
    ap.add_argument("--run", required=True, help="run folder containing manifest.jsonl")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="gemini-3.1-pro-preview", help="gemini only")
    ap.add_argument("--vertex", action="store_true", help="gemini via Vertex AI with Application Default Credentials")
    ap.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    ap.add_argument("--location", default="global")
    ap.add_argument("--temperature", type=float, default=0.0)
    a = ap.parse_args()
    man = [json.loads(l) for l in open(os.path.join(a.run, "manifest.jsonl"))]
    if a.limit:
        man = man[:a.limit]
    outdir = os.path.join(a.run, "judgments"); os.makedirs(outdir, exist_ok=True)
    name = "scribe_v2" if a.listener == "scribe" else "gemini_verifier"
    raw_p = os.path.join(outdir, f"{name}.raw.json")
    raw = json.load(open(raw_p)) if os.path.exists(raw_p) else {}
    items = [r for r in man if r.get("audio")]
    if a.listener == "scribe":
        key = os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            sys.exit("ELEVENLABS_API_KEY is not set")
        def stale(r):
            v = raw.get(r["id"]); return v is None or "error" in v or v.get("md5") != L.md5(r["audio"])
        def one(r):
            return r["id"], L.scribe_transcribe(r["audio"], key)
    else:
        client = L.make_gemini_client(a.vertex, a.project, a.location)
        def stale(r):
            v = raw.get(r["id"])
            return v is None or "error" in v or v.get("md5") != L.md5(r["audio"]) or v.get("model") != a.model or v.get("prompt_version") != L.PROMPT_VERSION
        def one(r):
            return r["id"], L.gemini_verify(client, a.model, r["audio"], r["text"], r["text_with_mark"], r["nvv"], a.temperature)
    todo = [r for r in items if stale(r)]
    print(f"{name}: {len(man)} prompts, {len(items)} recordings, {len(todo)} to judge", flush=True)
    lock = threading.Lock(); t0 = time.time(); n = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for f in as_completed([ex.submit(one, r) for r in todo]):
            rid, res = f.result()
            with lock:
                raw[rid] = res; n += 1
                if n % 10 == 0 or n == len(todo):
                    json.dump(raw, open(raw_p, "w"), ensure_ascii=False, indent=1)
                    print(f"  {n}/{len(todo)}  {(time.time() - t0) / 60:.1f} min", flush=True)
    json.dump(raw, open(raw_p, "w"), ensure_ascii=False, indent=1)
    errs = sum(1 for r in items if "error" in raw.get(r["id"], {"error": 1}))
    print(f"done: {len(items) - errs} judged, {errs} errors -> {raw_p}")
    if errs:
        print("re-run the same command to retry the errors before scoring"); sys.exit(2)


if __name__ == "__main__":
    main()
