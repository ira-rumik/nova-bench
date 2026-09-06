
# NoVA Methodology

This document states the scoring rules, the equations and the limitations behind the numbers in the README. Every table value is reproducible from `benchmark/judgments/` with `python aggregate.py --check`.

## 1. What is measured

Many TTS systems let the user write a tag such as `[laugh]` or `[sigh]` into the text, at the place where the sound should be. This benchmark measures how well those tags work: when a system is asked for a laugh, a chuckle or a sigh at a given word, does the sound come out, does it come out **at that word**, and does the system add sounds nobody asked for.

Three automatic listeners judge every clip, and every number is reported per listener. One score summarises rendering; a second table counts unrequested sounds.

![The evaluation pipeline.](figs/pipeline.png)

## 2. Prompt set

The prompts are the laugh, chuckle and sigh subsets of the NVV-SuperBench English evaluation set (Xue et al., 2026), taken verbatim: every sentence that carries exactly one tag, **149 prompts: 49 `<laugh>`, 50 `<chuckle>`, 50 `<sigh>`** (the one sentence with two tags was excluded). Sentences are 11–60 words long.

Every system receives the same text with the tag rewritten in the spelling its documentation prescribes:

| System | laugh | chuckle | sigh |
|---|---|---|---|
| Grok TTS | `[laugh]` | `[chuckle]` | `[sigh]` |
| Inworld TTS-2 | `[laugh]` | `[chuckle]` | `[sigh]` |
| Gemini 3.1 Flash TTS | `[laughs]` | `[chuckles]` | `[sighs]` |
| Orpheus 3B | `<laugh>` | `<chuckle>` | `<sigh>` |
| ElevenLabs v3 | `[laughs]` | `[chuckles]` | `[sighs]` |
| Cartesia Sonic 3.6 | `[laughter]` | `[laughter]` | n/a (no tag) |
| Rumik-OSS 1 | `<laugh>` | `<chuckle>` | `<sigh>` |

## 3. Systems

Seven systems, one fixed voice each, generated 4 September 2026:

- **Grok TTS** (xAI), voice *ara*: laugh, chuckle, sigh.
- **Inworld TTS-2**, voice *Ashley*: laugh, chuckle, sigh.
- **Gemini 3.1 Flash TTS** (Google), voice *Kore*: laugh, chuckle, sigh.
- **Orpheus 3B** (Canopy Labs, `orpheus-3b-0.1-ft`), voice *tara*: laugh, chuckle, sigh.
- **ElevenLabs v3**, voice *Jessica*, stability set to Creative (the documentation says to use Creative or Natural for audio tags): laugh, chuckle, sigh.
- **Cartesia Sonic 3.6**, voice *Monica*: a single `[laughter]` tag, used for both laugh and chuckle requests; no sigh tag, so sigh prompts are not sent and that class scores 0 (Section 6).
- **Rumik-OSS 1**, voice *Ira*, emotion descriptor *happy* for laugh and chuckle prompts and *sad* for sigh prompts: laugh, chuckle, sigh.

All other settings are the documented defaults.

## 4. Protocol

Each of the 149 prompts was synthesized **three times** per system (independent runs; a different seed per run where the system takes one), giving **447 clips per system** (Cartesia: 297, since its 50 sigh prompts are not sent). No generation failed. Each listener was run once on every clip. Nothing was re-generated or hand-picked.

## 5. Listeners

**silk-ASR (ours).** Rumik's in-house speech recognizer, which transcribes speech and writes `<laugh>`, `<chuckle>`, `<sigh>` inline where the sound occurs. It is not released; its per-recording judgments for the published systems are bundled in `benchmark/judgments/`. On the VocalSound corpus (3,504 speakers, one recording per speaker and class) it tags 94.9 % of the laughter recordings as laughter (laugh or chuckle) and 92.5 % of the sigh recordings as sigh. By our own listening, part of VocalSound is bad data, recordings that contain speech or music rather than the labelled sound, which a separate audio-event classifier (AST) also flagged. Decoding is deterministic; long clips are processed in windows.

**Scribe v2 (ElevenLabs).** ElevenLabs' speech-to-text service with audio-event tagging enabled; it returns a transcript with events such as `[laughs]`, `[chuckles]`, `[sighs]` at the position where they occur. Events are mapped to the three classes (`[laughs]`/`[laughter]`/`[giggles]` → laugh, `[chuckles]` → chuckle, `[sighs]` → sigh). It is ElevenLabs' model, and ElevenLabs is one of the benchmarked systems.

**Gemini verifier (NVV-SuperBench).** The verification method of NVV-SuperBench, run with the authors' released prompt and JSON schema verbatim: Gemini 3.1 Pro (temperature 0) receives the audio, the untagged reference text, the *target* tag, and the paper's 47-tag inventory as the allowed list, and answers whether the target occurs, inserting it once into the reference text at the location it hears, plus any *hallucinated events* (other tags it hears, without position). It is therefore told which tag to look for. Position = number of words before the inserted tag.

## 6. Scoring

## 6.1 From a transcript to a verdict (silk-ASR and Scribe v2)

Both the requested text (with its tag) and the listener transcript (with its tags) are normalised the same way: tags become single tokens; words are lower-cased with every non-alphanumeric character removed ("didn't," → "didnt"); tokens that were punctuation only are dropped. The requested position is then the number of words before the tag in this normalised sequence, so punctuation never shifts it.

The two token sequences are aligned by Levenshtein edit distance with tag-aware costs: word insert/delete 1.0, tag insert/delete 0.9, word↔word substitution 1.0, tag↔tag substitution 0.9, tag↔word substitution 3.0. The 0.9 makes a displaced tag re-insert rather than pair with the word it displaced; the 3.0 forbids a tag being matched to a word. Every transcript tag receives a position equal to the number of **reference** words consumed before it, so ASR word errors (a dropped or added word) do not move positions.

![Alignment and verdict on one clip (silk-ASR / Scribe v2 path).](figs/alignment.png)

The verdict for each request, from the positions:

- **rendered**: a tag of the requested class at the requested position;
- **wrong class**: a tag of another class at the requested position;
- **misplaced**: a tag of the requested class at another position;
- **not rendered**: none of the above.

Every listener tag left over after the verdict is an **unrequested sound**.

*Coverage gate.* Words spoken = reference words whose aligned transcript word is identical or a near-spelling (difflib ratio ≥ 0.8; substituting an unrelated word does not count). If fewer than 50 % of the requested words were spoken, the clip counts as not rendered whatever tags it carries. In the final run 1 clip of 2,979 failed the gate (Rumik-OSS 1, run 2).

*Laughter∪.* Laugh and chuckle are merged for the main table and the score: a laugh or a chuckle heard at the requested position counts as rendered for either request. The reason is in Section 7.3.

The Gemini verifier needs none of this: it returns the target tag's presence and position directly, and its hallucinated events are the unrequested sounds.

## 6.2 Rendered rate

For system $s$, listener $d$, class $c \in \{\text{laughter}\cup, \text{sigh}\}$ and run $r$:

$$\text{rendered}(s,d,c,r) = \frac{\#\{\text{class-}c\text{ requests with class }c\text{ heard at the requested position}\}}{\#\{\text{class-}c\text{ requests}\}}$$

with 99 laughter∪ requests (49 laugh + 50 chuckle) and 50 sigh requests per run. The table value is the mean over the three runs:

$$R(s,d,c) = \tfrac{1}{3}\sum_{r=1}^{3} \text{rendered}(s,d,c,r).$$

Worked example, Rumik-OSS 1 / silk-ASR / sigh: run 1 rendered 47 of 50 = 0.940, run 2 43 of 50 = 0.860, run 3 44 of 50 = 0.880, so $R = (0.940+0.860+0.880)/3 = 0.893$, printed as 0.89. Laughter∪ for the same pair: 87/99, 88/99, 81/99 → 0.862.

## 6.3 Unrequested sounds

$$\text{unrequested}(s,d) = \tfrac{1}{3}\sum_{r} \frac{\#\{\text{clips of run }r\text{ in which }d\text{ heard a laugh, chuckle or sigh that was not the one requested}\}}{\#\{\text{clips of run }r\}}$$

reported as a percentage of clips. This is NVV-SuperBench's "hallucinated events", expressed as a share of clips rather than folded into F1.

## 6.4 Score

$$S(s,d) = \frac{R(s,d,\text{laughter}\cup) + R(s,d,\text{sigh})}{2}, \qquad R(s,d,c) = 0 \text{ if } s \text{ has no tag for } c,$$

$$\text{Score}(s) = \frac{S(s,\text{silk-ASR}) + S(s,\text{Gemini}) + S(s,\text{Scribe})}{3}.$$

Systems are ordered by Score; ties are broken by the smaller share of clips with unrequested sounds. A class the system cannot be asked for counts as 0, so a laughter-only system cannot score above 0.5. The full arithmetic:

| Model | S(silk-ASR (ours)) | S(Gemini verifier) | S(Scribe v2) | Score |
|---|---|---|---|---|
| Grok (ara) | (1.00 + 1.00) / 2 = 0.998 | (1.00 + 0.99) / 2 = 0.997 | (1.00 + 0.84) / 2 = 0.920 | (0.998 + 0.997 + 0.920) / 3 = **0.972** |
| Inworld TTS-2 (Ashley) | (1.00 + 0.99) / 2 = 0.993 | (1.00 + 1.00) / 2 = 1.000 | (0.98 + 0.68) / 2 = 0.830 | (0.993 + 1.000 + 0.830) / 3 = **0.941** |
| Rumik-OSS 1 (Ira) | (0.86 + 0.89) / 2 = 0.878 | (0.92 + 0.96) / 2 = 0.941 | (0.87 + 0.80) / 2 = 0.833 | (0.878 + 0.941 + 0.833) / 3 = **0.884** |
| Orpheus 3B (tara) | (0.52 + 0.95) / 2 = 0.734 | (0.81 + 0.99) / 2 = 0.901 | (0.67 + 0.93) / 2 = 0.803 | (0.734 + 0.901 + 0.803) / 3 = **0.813** |
| ElevenLabs v3 (Jessica) | (0.40 + 0.86) / 2 = 0.630 | (0.83 + 0.97) / 2 = 0.902 | (0.33 + 0.84) / 2 = 0.583 | (0.630 + 0.902 + 0.583) / 3 = **0.705** |
| Gemini 3.1 Flash TTS (Kore) | (0.70 + 0.71) / 2 = 0.705 | (0.67 + 0.51) / 2 = 0.587 | (0.81 + 0.59) / 2 = 0.701 | (0.705 + 0.587 + 0.701) / 3 = **0.664** |
| Cartesia Sonic 3.6 (Monica) | (0.99 + 0.00) / 2 = 0.497 | (1.00 + 0.00) / 2 = 0.500 | (1.00 + 0.00) / 2 = 0.498 | (0.497 + 0.500 + 0.498) / 3 = **0.498** |

Score arithmetic. S(d) = (rendered laughter∪ + rendered sigh)/2 from Table 1; an absent class enters as 0. Score = mean of the three.

## 7. Results

## 7.1 Rendered at the requested position (Table 1)

| Model | Tags | silk-ASR (ours) laughter∪ | silk-ASR (ours) sigh | Gemini verifier laughter∪ | Gemini verifier sigh | Scribe v2 laughter∪ | Scribe v2 sigh | Score |
|---|---|---|---|---|---|---|---|---|
| Grok (ara) | L·C·S | 1.00 | **1.00** | **1.00** | 0.99 | **1.00** | 0.84 | **0.97** |
| Inworld TTS-2 (Ashley) | L·C·S | **1.00** | 0.99 | **1.00** | **1.00** | 0.98 | 0.68 | **0.94** |
| Rumik-OSS 1 (Ira) | L·C·S | 0.86 | 0.89 | 0.92 | 0.96 | 0.87 | 0.80 | **0.88** |
| Orpheus 3B (tara) | L·C·S | 0.52 | 0.95 | 0.81 | 0.99 | 0.67 | **0.93** | **0.81** |
| ElevenLabs v3 (Jessica) | L·C·S | 0.40 | 0.86 | 0.83 | 0.97 | 0.33 | 0.84 | **0.71** |
| Gemini 3.1 Flash TTS (Kore) | L·C·S | 0.70 | 0.71 | 0.67 | 0.51 | 0.81 | 0.59 | **0.66** |
| Cartesia Sonic 3.6 (Monica) | L | 0.99 | n/a | **1.00** | n/a | 1.00 | n/a | **0.50** |

Fraction of requests rendered at the requested word, mean of 3 synthesis runs, per listener. laughter∪ = a laugh or a chuckle accepted for either request. Tags: L laugh, C chuckle, S sigh accepted. Bold = best per column. “n/a” = no tag for that class. Score = mean over listeners of (laughter∪ + sigh)/2, an absent class counting 0.

Cells are 3-run means; the run-to-run standard deviation is at most 0.09 on every cell.

## 7.2 Clips containing a sound nobody asked for (Table 2)

| Model | silk-ASR (ours) | Gemini verifier | Scribe v2 |
|---|---|---|---|
| Grok (ara) | 0.7 % | 0.0 % | 0.0 % |
| Inworld TTS-2 (Ashley) | 0.0 % | 0.2 % | 0.0 % |
| Rumik-OSS 1 (Ira) | 2.9 % | 5.4 % | 4.5 % |
| Orpheus 3B (tara) | 0.0 % | 10.5 % | 0.4 % |
| ElevenLabs v3 (Jessica) | 1.1 % | 1.6 % | 0.0 % |
| Gemini 3.1 Flash TTS (Kore) | 19.0 % | 26.2 % | 21.5 % |
| Cartesia Sonic 3.6 (Monica) | 3.0 % | 0.0 % | 0.0 % |

Share of a system's clips in which the listener heard a laugh, chuckle or sigh that was not the one requested (mean of 3 runs; lower is better).

## 7.3 Laugh and chuckle separately (appendix table)

| Model | silk-ASR (ours) laugh | silk-ASR (ours) chuckle | silk-ASR (ours) sigh | Gemini verifier laugh | Gemini verifier chuckle | Gemini verifier sigh | Scribe v2 laugh | Scribe v2 chuckle | Scribe v2 sigh |
|---|---|---|---|---|---|---|---|---|---|
| Grok (ara) | 0.31 | 0.99 | **1.00** | **1.00** | **1.00** | 0.99 | **0.97** | 0.51 | 0.84 |
| Inworld TTS-2 (Ashley) | 0.07 | **1.00** | 0.99 | **1.00** | **1.00** | **1.00** | 0.89 | **0.63** | 0.68 |
| Rumik-OSS 1 (Ira) | 0.62 | 0.46 | 0.89 | 0.95 | 0.90 | 0.96 | 0.56 | 0.49 | 0.80 |
| Orpheus 3B (tara) | 0.16 | 0.50 | 0.95 | 0.80 | 0.83 | 0.99 | 0.55 | 0.25 | **0.93** |
| ElevenLabs v3 (Jessica) | 0.14 | 0.23 | 0.86 | 0.87 | 0.79 | 0.97 | 0.32 | 0.13 | 0.84 |
| Gemini 3.1 Flash TTS (Kore) | 0.47 | 0.57 | 0.71 | 0.66 | 0.67 | 0.51 | 0.69 | 0.39 | 0.59 |
| Cartesia Sonic 3.6 (Monica) | **0.71** | n/a | n/a | **1.00** | n/a | n/a | 0.94 | n/a | n/a |

Rendered as the exact requested class, per listener (mean of 3 runs). Bold = best per column.

The listeners disagree on the laugh/chuckle split of the same audio. On Grok's laugh requests, silk-ASR 0.31 laugh / 0.99 chuckle, Scribe v2 0.97 / 0.51, Gemini verifier 1.00 / 1.00, so the main table and the score merge the two classes.

## 8. Relation to NVV-SuperBench

Taken from NVV-SuperBench: the prompt set (their English laugh/chuckle/sigh items, verbatim), the Gemini verifier (their prompt, schema and allowed-tag inventory, run at temperature 0), and the notion of hallucinated events. Different from NVV-SuperBench: two additional listeners (an in-house tagging transcriber and a commercial ASR with audio events); a request counts only at the exact requested position, whereas their scoring accepts a match within δ = 2 words; a per-listener rendered rate and a score instead of precision/recall/F1.
