"""The two public listeners.

Scribe v2 (ElevenLabs speech-to-text with audio-event tagging): returns a transcript with events such as [laughs] /
[chuckles] / [sighs]; we rebuild one transcript string with those events converted IN PLACE to <laugh> / <chuckle> /
<sigh>, which is exactly the form evaluation.align scores. Events outside the three classes are dropped.

Gemini verifier (NVV-SuperBench protocol): the authors' prompt and JSON schema, verbatim, loaded from
evaluation/prompts/. The model receives the audio, the untagged reference text, the TARGET tag and the paper's tag
inventory as the allowed list, and returns whether the target occurs (inserting it once into the reference text at
the location it hears) plus any hallucinated events. Position = number of whitespace words before the inserted tag.
"""
import os, re, json, time, random, hashlib, unicodedata
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TAGS = ("laugh", "chuckle", "sigh")
ANGLE_TAG_RE = re.compile(r"<\s*([a-zA-Z0-9_]+)\s*>")


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------------------------------- Scribe v2
SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
EVENT_MAP = {"laughs": "laugh", "laughter": "laugh", "laughing": "laugh", "laugh": "laugh", "giggles": "laugh", "giggling": "laugh",
             "chuckles": "chuckle", "chuckle": "chuckle", "chuckling": "chuckle",
             "sighs": "sigh", "sigh": "sigh", "sighing": "sigh"}


def map_event(text):
    t = unicodedata.normalize("NFC", re.sub(r"^[\[\(\s]+|[\]\)\s]+$", "", str(text)).strip().lower())
    if t in EVENT_MAP:
        return EVENT_MAP[t]
    for k, v in EVENT_MAP.items():
        if k in t:
            return v
    return None


def rebuild(words):
    """Scribe words -> one string; audio events in place as canonical tags."""
    out = []
    for w in words or []:
        if w.get("type") == "audio_event":
            c = map_event(w.get("text", ""))
            if c:
                out.append(f" <{c}> ")
        elif w.get("type") == "word":
            out.append(w.get("text", ""))
        elif w.get("type") == "spacing":
            out.append(w.get("text", " "))
    return re.sub(r"\s+", " ", "".join(out)).strip()


def scribe_transcribe(audio_path, api_key, language_code="", retries=4):
    """One recording -> {"hyp", "text", "events", "words", "md5"} or {"error"}."""
    with open(audio_path, "rb") as f:
        audio = f.read()
    data = {"model_id": "scribe_v2", "tag_audio_events": "true"}
    if language_code:
        data["language_code"] = language_code
    last = None
    for attempt in range(retries):
        try:
            resp = requests.post(SCRIBE_URL, headers={"xi-api-key": api_key}, data=data,
                                 files={"file": (os.path.basename(audio_path), audio, "audio/wav")}, timeout=180)
            if resp.status_code == 200:
                j = resp.json(); words = j.get("words") or []
                return {"hyp": rebuild(words), "text": (j.get("text") or "").strip(),
                        "events": [w.get("text") for w in words if w.get("type") == "audio_event"],
                        "words": [{k: w.get(k) for k in ("text", "type")} for w in words], "md5": md5(audio_path)}
            last = f"HTTP {resp.status_code}: {resp.text[:120]}"
            if resp.status_code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(3 * (attempt + 1)); continue
            break
        except Exception as e:  # network errors: retry
            last = str(e)[:120]; time.sleep(2 * (attempt + 1))
    return {"error": last}


# ------------------------------------------------------------------------------------------------ Gemini verifier
PROMPT_TEMPLATE = open(os.path.join(HERE, "prompts", "nvv_superbench_verifier_v1.txt")).read()
ALLOWED_TAGS = json.load(open(os.path.join(HERE, "prompts", "allowed_tags.json")))["tags"]
PROMPT_VERSION = "nvv_superbench_verifier_v1"
RESPONSE_SCHEMA = {  # verbatim from NVV-SuperBench predict_nvc.py
    "type": "object",
    "properties": {
        "present": {"type": "boolean"},
        "text_with_mark": {"type": "string"},
        "confidence": {"type": "number"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "hallucinated": {"type": "boolean"},
        "hallucinated_events": {"type": "array", "items": {"type": "object",
            "properties": {"tag": {"type": "string"}, "location_hint": {"type": "string"}},
            "required": ["tag", "location_hint"]}},
    },
    "required": ["present", "text_with_mark", "hallucinated", "hallucinated_events"],
}


def build_verify_prompt(ref_text, target_tag):
    return PROMPT_TEMPLATE.replace("{TARGET_TAG}", target_tag).replace("{ALLOWED_TAGS}", ", ".join(f"<{t}>" for t in ALLOWED_TAGS)).replace("{REFERENCE_TEXT}", ref_text)


def make_gemini_client(vertex=False, project=None, location="global", api_key=None):
    from google import genai
    if vertex:
        if not project:
            raise SystemExit("--project is required with --vertex (or set GOOGLE_CLOUD_PROJECT)")
        return genai.Client(vertexai=True, project=project, location=location)
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set (or use --vertex)")
    return genai.Client(api_key=key)


def _strip_tags_norm(s):
    return re.sub(r"\s+", " ", ANGLE_TAG_RE.sub("", s or "")).strip()


def _insert_index(text_with_mark, tag):
    k = text_with_mark.find(f"<{tag}>")
    return None if k < 0 else len(text_with_mark[:k].split())


def _normalize_hallu(ev):
    out = []
    for e in (ev or [])[:2]:
        if not isinstance(e, dict):
            continue
        t = e.get("tag", ""); m = ANGLE_TAG_RE.search(t) if isinstance(t, str) else None
        name = m.group(1) if m else (t.strip().strip("<>").strip() if isinstance(t, str) else "")
        if name:
            out.append({"tag": f"<{name}>", "location_hint": e.get("location_hint", "") if isinstance(e.get("location_hint"), str) else ""})
    return out


def gemini_verify(client, model, audio_path, ref_text, text_with_mark, target, temperature=0.0, retries=3):
    """One recording -> NVV-SuperBench prediction record (or {"error"}). Retries when the reference text was altered or
    the present flag and the inserted tag disagree, as the authors' code does."""
    from google.genai import types
    cfg = types.GenerateContentConfig(temperature=temperature, response_mime_type="application/json", response_json_schema=RESPONSE_SCHEMA)
    prompt = build_verify_prompt(ref_text, target)
    with open(audio_path, "rb") as f:
        audio = f.read()
    last = None
    for attempt in range(retries + 1):
        try:
            resp = client.models.generate_content(model=model, config=cfg, contents=[prompt, types.Part.from_bytes(data=audio, mime_type="audio/wav")])
            txt = resp.text or ""
            obj = json.loads(txt) if txt.strip().startswith("{") else json.loads(re.search(r"\{[\s\S]*\}", txt).group(0))
            twm = obj.get("text_with_mark", ref_text) or ref_text
            if _strip_tags_norm(twm) != _strip_tags_norm(ref_text):
                last = f"reference altered: {twm[:80]!r}"; raise ValueError(last)
            present = bool(obj.get("present", False)); n_tag = twm.count(f"<{target}>")
            if (present and n_tag != 1) or (not present and n_tag != 0):
                last = f"inconsistent present={present} with {n_tag} tags"; raise ValueError(last)
            k = _insert_index(twm, target) if present else None
            L = len(ref_text.split()); gt = _insert_index(text_with_mark, target)
            return {"text": ref_text, "text_with_mark": twm, "target_tag": f"<{target}>", "present": present, "pos_unit": "word",
                    "pred_pos": ({"index": k, "n_units": L} if (present and k is not None) else None), "gt_pos": {"index": gt, "n_units": L},
                    "hallucinated": bool(obj.get("hallucinated", False)), "hallucinated_events": _normalize_hallu(obj.get("hallucinated_events")),
                    "confidence": obj.get("confidence"), "md5": md5(audio_path), "model": model, "prompt_version": PROMPT_VERSION, "attempts": attempt + 1}
        except Exception as e:
            last = str(e)[:200]; time.sleep(min(12, 1.5 * (2 ** attempt)) * (0.7 + random.random() * 0.6))
    return {"error": last}


def gemini_record(item, pred, verdict_fn, fold_fn):
    """Turn one verifier prediction into the shared per-recording record (positions in whitespace words)."""
    base = {"id": item["id"], "system": item.get("system"), "run": item.get("run"), "listener": "gemini_verifier", "nvv": item["nvv"]}
    if not item.get("audio"):
        base.update({"gt_index": None, "valid": False, "listener_error": False, "hyp_tags": [], "verdict_3class": "not_rendered",
                     "verdict_2class": "not_rendered", "spurious_3class": [], "spurious_2class": []})
        return base
    if pred is None or "error" in pred:
        base.update({"listener_error": True}); return base
    gt = pred["gt_pos"]["index"]; k = pred["pred_pos"]["index"] if pred.get("pred_pos") else None
    hall = [ANGLE_TAG_RE.search(e["tag"]).group(1) for e in pred["hallucinated_events"] if ANGLE_TAG_RE.search(e["tag"])]
    hyp_tags = ([{"cls": item["nvv"], "index": k}] if k is not None else []) + [{"cls": h, "index": -1} for h in hall if h in TAGS]
    base.update({"gt_index": gt, "n_words": pred["gt_pos"]["n_units"], "valid": True, "listener_error": False, "hyp_tags": hyp_tags,
                 "pred_class": item["nvv"] if k is not None else None, "pred_index": k, "confidence": pred.get("confidence")})
    for view in ("3class", "2class"):
        v, sp = verdict_fn(item["nvv"], gt, hyp_tags, view, True)
        base[f"verdict_{view}"] = v; base[f"spurious_{view}"] = sp
    return base
