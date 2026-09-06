#!/usr/bin/env python3
"""NoVA figures in the figures4papers house style (matplotlib, Helvetica/Arial, spines off, fixed palette, 300 dpi).
Reads benchmark/judgments; writes figs/*.png (unrequested_sounds, pipeline, alignment). The score chart figs/nova_scores.png is a separate asset."""
import json, os, statistics as st, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__)); FIGS = f"{HERE}/figs"; os.makedirs(FIGS, exist_ok=True)
JUD = f"{HERE}/benchmark/judgments"
PALETTE = {"blue_main": "#0F4D92", "blue_secondary": "#3775BA", "green_3": "#8BCF8B", "green_2": "#AADCA9", "red_strong": "#B64342",
           "red_2": "#E9A6A1", "neutral": "#CFCECE", "teal": "#42949E", "violet": "#9A4D8E", "gray": "#767676", "dark": "#272727"}
plt.rcParams.update({"font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"], "font.size": 16, "axes.spines.right": False,
                     "axes.spines.top": False, "axes.linewidth": 2, "legend.frameon": False, "svg.fonttype": "none"})
SYS = [("grok", "Grok\n(ara)"), ("inworld_tts2", "Inworld TTS-2\n(Ashley)"), ("rumik_oss_1", "Rumik-OSS 1\n(Ira)"), ("orpheus_3b", "Orpheus 3B\n(tara)"),
       ("elevenlabs_v3", "ElevenLabs v3\n(Jessica)"), ("gemini_3_1_flash_tts", "Gemini 3.1 Flash TTS\n(Kore)"), ("cartesia_sonic_3_6", "Cartesia Sonic 3.6\n(Monica)")]
SHORT = {"grok": "Grok", "inworld_tts2": "Inworld\nTTS-2", "rumik_oss_1": "Rumik-OSS 1", "orpheus_3b": "Orpheus 3B", "elevenlabs_v3": "ElevenLabs\nv3", "gemini_3_1_flash_tts": "Gemini 3.1\nFlash TTS", "cartesia_sonic_3_6": "Cartesia\nSonic 3.6"}
DET = [("silk_asr", "silk-ASR (ours)", PALETTE["blue_main"]), ("gemini_verifier", "Gemini verifier", PALETTE["teal"]), ("scribe_v2", "Scribe v2", PALETTE["red_strong"])]
def fold(c): return "laughter" if c in ("laugh", "chuckle") else c
def recs(s, r, d): return [json.loads(l) for l in open(f"{JUD}/{s}/{r}/{d}.jsonl")]
R, SP, SC = {}, {}, {}
for s, _ in SYS:
    for d, _, _ in DET:
        for c in ("laughter", "sigh"):
            v = []
            for r in ("r1", "r2", "r3"):
                rows = [x for x in recs(s, r, d) if fold(x["nvv"]) == c]
                if rows: v.append(sum(x["verdict_2class"] == "rendered" for x in rows) / len(rows))
            R[(s, d, c)] = st.mean(v) if v else None
        SP[(s, d)] = st.mean(100 * sum(1 for x in recs(s, r, d) if x["spurious_2class"]) / len(recs(s, r, d)) for r in ("r1", "r2", "r3"))
    SC[s] = st.mean(((R[(s, d, "laughter")] or 0) + (R[(s, d, "sigh")] or 0)) / 2 for d, _, _ in DET)
ORDER = sorted([s for s, _ in SYS], key=lambda s: -SC[s]); LABEL = dict(SYS)
def save(fig, name, pad=1.5):
    fig.tight_layout(pad=pad)
    fig.savefig(f"{FIGS}/{name}.png", dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig); print("wrote", name)

# ---------- Figure C: unrequested sounds per listener
w = 0.26
fig, ax = plt.subplots(figsize=(14, 5.2))
for j, (d, dn, col) in enumerate(DET):
    ys = [SP[(s, d)] for s in ORDER]
    ax.bar([i + (j - 1) * w for i in range(len(ORDER))], ys, width=w, color=col, edgecolor="black", linewidth=1.2, label=dn)
ax.set_xticks(range(len(ORDER))); ax.set_xticklabels([SHORT[s] for s in ORDER], fontsize=13)
ax.set_ylabel("clips with an unrequested sound  (%)  (↓)", fontsize=15, labelpad=10); ax.tick_params(width=1.5, length=6)
ax.legend(loc="upper left", fontsize=14); ax.set_ylim(0, 30)
save(fig, "unrequested_sounds")

# ---------- helpers for diagrams
def box(ax, x, y, w_, h, title, lines, fc="white", ec=PALETTE["dark"], ts=15, ls=12.5, lw=1.8):
    ax.add_patch(FancyBboxPatch((x, y), w_, h, boxstyle="round,pad=0.02,rounding_size=0.25", fc=fc, ec=ec, lw=lw))
    ax.text(x + w_ / 2, y + h - 0.32, title, ha="center", va="top", fontsize=ts, fontweight="bold", color=PALETTE["dark"])
    for k, l in enumerate(lines): ax.text(x + w_ / 2, y + h - 0.32 - 0.42 * (k + 1), l, ha="center", va="top", fontsize=ls, color=PALETTE["dark"])
def arrow(ax, x1, y1, x2, y2, lw=1.8): ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=18, lw=lw, color=PALETTE["dark"]))
def canvas(w_, h): 
    fig, ax = plt.subplots(figsize=(w_, h)); ax.set_xlim(0, w_); ax.set_ylim(0, h); ax.axis("off"); return fig, ax

# ---------- Figure D: pipeline
fig, ax = canvas(20, 5.4)
y, h = 1.9, 2.2
box(ax, 0.3, y, 3.4, h, "149 prompts", ["NVV-SuperBench, English", "laugh 49 · chuckle 50 · sigh 50", "one tag per sentence"], fc="#FFF8DC")
arrow(ax, 3.75, y + h / 2, 4.35, y + h / 2)
box(ax, 4.4, y, 3.6, h, "7 TTS systems", ["one fixed voice each", "tag in the system's own spelling", "3 synthesis runs → 447 clips"], fc="#EEF3FF")
arrow(ax, 8.05, y + h / 2, 8.65, y + h / 2)
ax.add_patch(FancyBboxPatch((8.7, y - 0.55), 4.0, h + 1.15, boxstyle="round,pad=0.02,rounding_size=0.25", fc="#F7F7F2", ec="#BBBBBB", lw=1.2, ls="--"))
ax.text(10.7, y + h + 0.42, "three listeners, each hears every clip", ha="center", va="center", fontsize=12, color=PALETTE["gray"])
for k, (name, col) in enumerate([("silk-ASR (ours)", "#E8F5E9"), ("Scribe v2 (ElevenLabs)", "#E8F5E9"), ("Gemini verifier (NVV-SuperBench)", "#FFF3E0")]):
    yy = y + h - 0.62 - k * 0.78
    ax.add_patch(FancyBboxPatch((8.9, yy - 0.1), 3.6, 0.6, boxstyle="round,pad=0.02,rounding_size=0.2", fc=col, ec=PALETTE["dark"], lw=1.4))
    ax.text(10.7, yy + 0.2, name, ha="center", va="center", fontsize=12.5, fontweight="bold", color=PALETTE["dark"])
arrow(ax, 12.75, y + h / 2, 13.35, y + h / 2)
box(ax, 13.4, y, 3.3, h, "Verdict per request", ["rendered at the word", "misplaced · wrong class", "not rendered · unrequested sound"])
arrow(ax, 16.75, y + h / 2, 17.35, y + h / 2)
box(ax, 17.4, y, 2.3, h, "Tables", ["rendered rate", "unrequested sounds", "score"], fc="#F3E8FF")
ax.text(10, 0.95, "every number is reported per listener;  score = mean over listeners of (rendered laughter∪ + rendered sigh) / 2,  a class without a tag counting 0", ha="center", va="center", fontsize=12.5, color=PALETTE["dark"])
ax.text(10, 0.45, "laughter∪ = a laugh or a chuckle accepted for either request", ha="center", va="center", fontsize=12, color=PALETTE["gray"])
save(fig, "pipeline", pad=0.5)

# ---------- Figure E: alignment → verdict (example verified against the scorer)
sys.path.insert(0, HERE); from evaluation import align as B
ref = "the printer has done that again <laugh> and nobody knows why"; hyp = "the printer done that again <chuckle> and nobody knows why <sigh>"
rt, ht, _ = B.analyse_clip(ref, hyp); assert rt[0]["index"] == 6 and ht[0]["index"] == 6 and B.verdict("laugh", 6, ht, "3class")[0] == "wrong_class"
fig, ax = canvas(20, 7.4)
def row(y0, toks, label, tagcol):
    ax.text(0.4, y0 + 0.95, label, fontsize=15, fontweight="bold", color=PALETTE["dark"], va="bottom"); xs = []
    for i, t in enumerate(toks):
        x = 0.4 + i * 1.72; xs.append(x + 0.76)
        ax.add_patch(FancyBboxPatch((x, y0), 1.52, 0.62, boxstyle="round,pad=0.02,rounding_size=0.15", fc=(tagcol if t.startswith("<") else "white"), ec=PALETTE["dark"], lw=1.4))
        ax.text(x + 0.76, y0 + 0.31, t, ha="center", va="center", fontsize=13, color=PALETTE["dark"])
    return xs
RT, HT = ref.split(), hyp.split()
xr = row(5.6, RT, "requested text: the tag is a token like a word", "#FFF8DC")
xh = row(3.5, HT, "what the listener wrote", "#E8F5E9")
for op, i, j in B.align(B.toks(ref), B.toks(hyp)):
    if op == "match": ax.plot([xr[i], xh[j]], [5.6, 4.12], color="#999999", lw=1)
    if op == "sub": ax.plot([xr[i], xh[j]], [5.6, 4.12], color=PALETTE["red_strong"], lw=1.8, ls="--")
ax.text(xr[2] - 1.0, 4.85, "“has” not transcribed → skipped,\nstill counted as a requested word", fontsize=11.5, color=PALETTE["gray"], ha="center", va="center", bbox=dict(fc="white", ec="none", pad=2))
ax.text(xr[6] + 0.3, 4.3, "requested tag ↔ heard tag of another class", fontsize=11.5, color=PALETTE["red_strong"], ha="center", va="center", bbox=dict(fc="white", ec="none", pad=2))
ax.text(xh[10], 3.2, "extra tag → unrequested sound", fontsize=11.5, color=PALETTE["gray"], ha="center", va="center")
yb, hb = 0.35, 2.15
box(ax, 0.4, yb, 6.1, hb, "Position = requested words before the tag", ["requested <laugh>: the printer has done that again → 6", "heard <chuckle>: same 6 requested words before it → 6", "the skipped “has” still counts, so positions never shift"], ls=12)
box(ax, 6.9, yb, 6.2, hb, "Verdict for this request", ["position 6: asked laugh, heard chuckle → wrong class", "(laughter∪ view: laugh or chuckle → rendered)", "same class elsewhere → misplaced;  none → not rendered"], ls=12)
box(ax, 13.5, yb, 6.1, hb, "Alignment costs", ["word missing/extra 1.0 · tag missing/extra 0.9", "word↔word 1.0 · tag↔tag 0.9 · tag↔word 3.0", "so a tag is never lined up against a word"], ls=12)
save(fig, "alignment", pad=0.5)
print("done")
