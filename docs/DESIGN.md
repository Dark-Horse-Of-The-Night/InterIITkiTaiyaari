# Design decisions and evaluation

This document explains *why* the AI Meeting Assistant is built the way it is. Most decisions were made by measuring something first; the numbers are included. For setup and usage, see the [README](../README.md).

## Contents
1. [Architecture](#1-architecture)
2. [Stage 1: speech-to-text](#2-stage-1-speech-to-text)
3. [Stage 2: refiner](#3-stage-2-refiner)
4. [Stage 3: documenter](#4-stage-3-documenter)
4b. [Speakers: labels and names](#4b-speakers-labels-and-names)
5. [Long meetings](#5-long-meetings)
6. [Reliability: timeouts, retries, rate limits](#6-reliability-timeouts-retries-rate-limits)
7. [Web app](#7-web-app)
8. [Evaluation](#evaluation)
9. [What I'd do next](#9-what-id-do-next)

---

## 1. Architecture

- **Three separate stages** (`stt.py` → `refiner.py` → `documenter.py`), each with its own model setting (`STT_*`, `REFINER_*`, `DOCUMENTER_*`) and prompt file. The order is defined in one place, [`run.py`](../backend/app/pipeline/run.py), which both the web app and the command-line scripts use.
- **The pipeline never imports FastAPI.** The web layer ([`main.py`](../backend/app/main.py)) only handles uploads, jobs and HTTP errors, so the pipeline can be tested and run on its own.
- **One SDK for every provider.** All calls use the OpenAI Python SDK with `base_url`, so switching provider is a `.env` change.
- **Every user-facing error is a `PipelineError(stage, problem, fix)`.** The message always says which stage failed, what happened and what to do, e.g. *"Refiner failed: the API key was rejected. Check REFINER_API_KEY in backend/.env."*
- **Model choice was verified against the live account.** Groq's docs page listed `llama-3.3-70b-versatile`, but the account's model list showed it was retired. Both LLM stages use `openai/gpt-oss-120b`, which also supports strict JSON-schema output.

## 2. Stage 1: speech-to-text

**File checks before any AI call** ([`audio.py`](../backend/app/pipeline/audio.py)): extension, empty file, size limit, and an `ffprobe` check that the file really contains audio with a duration. A text file renamed to `.mp3` is rejected with *"the file could not be read as audio (it may be corrupt or not really an audio file)"*.

**Format sent to Whisper: 16 kHz mono Opus at 32 kbps.** This was measured on a 13.4-minute meeting:

| Format | Size | Time to transcript | Word error rate vs. script |
|---|---|---|---|
| FLAC (lossless) | 16.5 MB | 41.9 s | 2.11% |
| Opus 32 kbps | 3.0 MB | 12.3 s | 2.07% |

Same accuracy at one fifth of the size; upload was the bottleneck. (This also uncovered a bug: ffmpeg was writing **24-bit** FLAC from compressed input, 43% bigger than needed.) Caveat: measured on clean synthetic speech.

**Splitting long recordings** into ~5-minute parts:
- Each cut is placed in the **latest pause** (≥ 0.2 s of silence, found with ffmpeg's `silencedetect`) within the 20 s before each 5-minute mark, so words aren't cut in half. With no pause, it cuts exactly at the mark. A tiny final part is merged into the previous one.
- 0.2 s was chosen after measuring: pauses between sentences in the test audio were 0.22–0.27 s, so the original 0.4 s threshold found **none**.
- 5 minutes (not 10) because on a slow connection (74 KB/s at one point) 2.3 MB uploads were dropped repeatedly. 1.1 MB parts upload faster, and a retry re-sends less.
- Timestamps of each part are shifted so the transcript reads as one continuous meeting.

## 3. Stage 2: refiner

**Job:** fix misrecognised technical terms only. The hard part is guaranteeing it *doesn't* change meaning.

**The model returns only the segments it changed** (anything omitted stays as it was). This was a measured change:

| Format | Output tokens (one 39-segment batch) | What came back |
|---|---|---|
| Return every segment | 2,779 | All 39, but **3 silently damaged**: punctuation stripped from one, words moved between two others |
| Changed segments only + `reasoning_effort="low"` | **355** | Nothing (correct: that batch had no misheard terms) |

An omitted segment can never change meaning, so this is both cheaper and safer.

**Code checks every edit** ([`refiner.py`](../backend/app/pipeline/refiner.py) `check_edit`). An edit is discarded, the original wording kept, and a warning shown if it:
- changes any **number** ("five" and "5" count as the same number, so `S three → S3` is allowed)
- changes any **negation** (not, never, nobody, haven't…, including curly apostrophes)
- changes any **commitment word** (will, should, might, maybe, decided, agreed, proposed…). This was added after testing showed "should ship → must ship" slipped past the other checks
- changes **sentence punctuation**
- **rewrites too much**: many words changed *and* letter similarity below 0.85. Measured: genuine multi-term fixes scored 0.86–0.98 ("oh auth with jason web tokens" → "OAuth with JSON Web Tokens"); a real rewrite scored 0.35.

The corrections list (`CICD → CI/CD`) is computed by code from a word diff, not taken from the model.

**Spacing and capitalisation of product names.** The first version missed names spelled right but spaced or capitalised wrong. On the 13-minute meeting the raw transcript still contained "open telemetry" (4×) and "Launch Darkly". The prompt now covers this, using *different* example terms (Elasticsearch, DynamoDB, Next.js) so the test terms stay unseen. Result on that meeting: it now fixes `open telemetry → OpenTelemetry` and `launch darkly → LaunchDarkly`. Low reasoning effort beat medium: 6 vs 5 fixes, 1,164 vs 2,199 output tokens, 12 s vs 51 s, and medium made one edit that broke a negation, which the checks caught.

**Terms split across segments.** Whisper split "open | telemetry" across two segments. Fixing the first to "OpenTelemetry" would leave "OpenTelemetry telemetry". Words can't move between segments (timestamps belong to them), so a new check rejects any edit that would repeat a word continuing in the next segment, or starting in the previous one.

**Trap test** (a hand-written transcript with misheard terms plus traps): fixed Kubernetes, PostgreSQL, MongoDB, GitHub Actions, OAuth, JSON Web Tokens, TypeScript and S3. It left alone "Jenkins from the platform team" (a person), "Ruby said…" (a person), "fifteen thousand", "two more sprints", "not switching" and "nobody agreed".

## 4. Stage 3: documenter

**Strict structured output.** The model must follow the JSON schema of `MeetingRecord`; fields filled by code (timestamps, warnings) are left out of the schema. Invalid output is retried once, then reported.

**Every item needs evidence:** segment ids plus a short **exact quote**. Then code verifies the record against the transcript ([`documenter.py`](../backend/app/pipeline/documenter.py) `verify_record`):
- **Quote not in the transcript** (case and punctuation ignored, may span neighbouring segments): the item is **removed**, with a note. The segment ids and timestamp are taken from where the quote actually is, not from what the model claimed.
- **Owner:** every word of the name must appear in the cited lines or the 2 lines before (so "Priya said… so she will…" keeps Priya). Otherwise the owner is set to `null`. Pronouns and "someone/nobody" are always `null`.
- **Deadline:** must appear word for word near the quote. "by Friday" turned into "2026-10-09" is removed, because the meeting date is unknown.

**Classification rules** in [`documenter.md`](../backend/app/prompts/documenter.md): a decision needs agreement; **postponing is not deciding** (added after a test recorded "we agreed to think about it" as a decision); a proposal is not a decision; an unaccepted suggestion is not a task; a reversal keeps only the final outcome. "Someone needs to update the docs" with no volunteer is an action item with owner Unspecified, so the gap stays visible.

**Markdown is rendered by code** ([`render.py`](../backend/app/pipeline/render.py)), not by the LLM, so Markdown and JSON always contain the same items.

## 4b. Speakers: labels and names

The problem statement asks for real speaker names where they can be worked out, and labels otherwise. Whisper doesn't identify speakers, so this is two steps:

1. **Who spoke (stage 1, [`speakers.py`](../backend/app/pipeline/speakers.py)).** A local voice model (SpeechBrain ECAPA, ~90 MB, no account needed) turns each Whisper segment into a voice fingerprint. Segments are grouped by average-linkage clustering on cosine distance (plain NumPy) and numbered in order of first speaking: **Speaker 1, Speaker 2…** Segments under 0.8 s borrow the previous label. These labels appear in the **raw** transcript. The packages are optional: without them, transcripts have no labels.
2. **Real names (stage 2, [`speaker_names.py`](../backend/app/pipeline/speaker_names.py)).** One LLM call proposes names with evidence. **Code accepts a name only if:**
   - the quote really is in the transcript and contains the name; and
   - either it's a **self-introduction** in that speaker's own line ("this is Tom…", "I'm Priya"), or another speaker says the name **to someone** (name followed by a comma or question mark: "Neha, can you…?", "…take a look, Neha?") and the **next different voice** is that speaker.
   - Two names for one voice, or one name for two voices, means neither is used.
   - A name that's only mentioned ("Rahul said yesterday…") is rejected. The tests caught an early version that would have accepted it.

   Names replace labels in the **refined** transcript. That is also what makes raw and refined differ even when Whisper heard every term correctly.
3. **Owners.** The documenter sees who said each line. "I'll have a fix ready by Friday" spoken by an identified *Neha* makes Neha the owner, and the owner check counts a line's identified speaker as "stated". From an unnamed "Speaker 2", "I" is still unknown, so the owner stays Unspecified; a label is never an owner.

## 5. Long meetings

Groq's free tier allows **8,000 tokens per minute** per model, for every chat model on the account (checked from response headers). A single documenter request for even a **48-second** meeting used 4,178 tokens (≈1,800 prompt and schema overhead, ≈1,600 hidden reasoning), so a single request can't cover more than a few minutes of transcript.

**Design: document in parts, join in code, cross-check with a small request** ([`merge.py`](../backend/app/pipeline/merge.py)):
1. The transcript is split into **balanced parts** that fit `DOCUMENTER_MAX_REQUEST_TOKENS` (default 7,500), with half of each request kept for the reply. Lines keep their global numbers, so evidence ids stay valid.
2. Each part is documented with the normal prompt plus "this is part N of M".
3. If a reply is **cut off** at the output limit, that part is **split in half** and retried, rather than repeating an identical request.
4. Code **joins** the parts: minutes in order (a topic spanning a boundary becomes one topic), plus all items.
5. One **cross-check** request sees a one-line list of all items (`[O1] (part 1) Proposal: …`) and may **only remove** items, naming the later item that replaces each: `accepted_later`, `answered_later`, `superseded` or `duplicate`. Code validates each removal: the items exist, the kinds make sense (only a proposal can be "accepted"), the replacement is later, and there are no removal chains. Each applied removal becomes a visible note.
6. The usual quote, owner and deadline checks run on the merged record against the **whole** transcript.

*Why not let an LLM merge the partial records?* The merged input grows with the meeting and would exceed the free-tier request limit at about 25–30 minutes. It could also reword items during merging. The cross-check input is a few lines per item, and it can't add or change anything. If even that list is too large, the app skips the cross-check and adds a visible note rather than failing.

## 6. Reliability: timeouts, retries, rate limits

[`retry.py`](../backend/app/pipeline/retry.py) replaces the SDK's silent retries (`max_retries=0`) with visible ones:

| Problem | Behaviour |
|---|---|
| Timeout | 1 retry. Timeouts: connect 10 s; speech-to-text 60 s + 2 s per audio minute; refiner 60 s; documenter 90 s |
| Connection failure, 5xx | 2 retries, waiting 2 s then 5 s |
| Rate limit (429) | Up to 6 retries, waiting the service's `Retry-After` (≤ 60 s) |
| Rate limit asking for a **long** wait (e.g. the daily limit: "try again in 29m") | No retry. Error says which limit and roughly when to try again |
| Request too large (413) | No retry. "This meeting is too long for the AI service's per-minute limit…" |
| Bad key / unknown model / bad request | No retry. Error names the `.env` setting to check |

Every retry appears in the app under the running step (*"Reached the AI service's rate limit (free tier). Waiting 14s, then trying again (1 of 6)…"*) and in the server log. If a step reports no progress for 20 s, the app shows *"Taking longer than usual. The AI service may be busy."*

Before this change, a hung service could leave the app spinning for ~15 minutes with no message. Tested against a local server that accepts connections but never answers: hint at 20 s, retry note at ~61 s, clear error at ~125 s.

## 7. Web app

- **Upload → job → poll.** `POST /api/meetings` checks the file immediately (bad files fail in under a second) and returns a job id; processing runs in the background; the frontend polls once a second and shows each stage's state, "Part N of M", retry notes and timings.
- **Upload limits** are enforced twice: from `Content-Length` before the body is read, and by counting bytes while saving. Temporary files are always deleted.
- **Downloads** are generated in the browser from data already received; the server stores nothing.
- **Frontend** is React + Vite + TypeScript with Tailwind CSS, designed first as mockups (the "Ledger" look: Geist type, one teal accent, evidence quotes with timestamp chips, Unspecified as a visible dashed tag). It follows the system's light or dark mode and works at phone width. Speakers appear at the start of each turn, with a sidebar explaining how each name was identified.

## Evaluation

All test meetings were generated with macOS `say` from known scripts ([`scripts/make_test_meeting.py`](../scripts/make_test_meeting.py)), so the script is the ground truth. Synthetic speech is cleaner than real meetings, so accuracy on real recordings will be lower.

| Test | Result |
|---|---|
| **`samples/meeting`** (33 s) | ✅ Decision: OAuth/JWT · Action: Priya, PostgreSQL migration, by Friday · Action: Swagger docs, **Unspecified** owner · Arjun's GitHub Actions idea → **open proposal**, not a decision · `CICD → CI/CD` |
| **`samples/hard_meeting`** (48 s) | ✅ Proposal accepted later → **decision** (Mixpanel), not also an open item · reversed plan → final outcome only (Dark Mode next release) · "Neha, can you… by March 3rd?" "Sure, I'll…" → owner Neha, deadline as spoken · "I'll take care of the beta list" → **Unspecified** · "Maybe John could look at…?" (no reply) → open proposal, John *not* listed as raiser · unanswered question → open question |
| **13-minute meeting**, two-step documenter | ✅ Documented in 4 parts (one automatically split after a cut-off) + cross-check, ~5 min on the free tier. All **7/7** action items with correct owner and deadline, all **4/4** decisions, all **5** distinct proposals, with repeats across parts merged. ❌ Two "we agreed to think about it" statements were recorded as decisions. This led to the "postponing is not deciding" rule, which has **not yet been re-verified** on this meeting |
| **35-minute meeting with cross-part traps** | ⚠️ **Partial.** Transcription (8 parts) and refiner (11 batches) completed in the browser with live progress. The documenter reached part 3 of 10 and then hit the free tier's **daily** token limit (197,464 / 200,000 used during development). The cross-part traps (proposal in part 1 accepted at 70%, decision reversed at 90%, owner + deadline at 30%) are covered by unit tests with fake model replies, but not yet verified with the real model |
| **5-voice meeting, speaker naming** (`scripts/make_speaker_meeting.py`, 56 s; true labels supplied to isolate the naming step) | ✅ **3/3** provable names in 2/2 runs: Neha and Rahul (addressed, then answer) and Tom (self-introduction). The host and the questioner, never named, stay **Speaker 1 / Speaker 5**. Documenter: crash fix → **Neha**, by Friday; Mixpanel account → **Tom**, this week; release notes → **Unspecified** (Neha declined). The answered App Store question correctly isn't an open item. The first prompt version found only 2/3; asking it to check every addressed name fixed that |
| **Error handling** | ✅ Text file renamed `.mp3` · empty file · unsupported format · oversized upload · no file · unknown job · wrong key · rate limits · hung service · daily limit: each gives a specific stage + message + fix |
| **Automated tests** | ✅ 168 backend (pytest) + 27 frontend (Vitest) |

**Run-to-run variation.** LLM output varies slightly even at temperature 0 (e.g. "by March 3rd" vs "March 3rd", different task wording). Across repeated runs of `hard_meeting`, the classification (decision vs proposal, owners, Unspecified) stayed the same.

**Token cost.** Roughly: refiner ≈ 2,500 tokens per 40-segment batch; documenter ≈ 4,000–7,500 per part. A ~35-minute meeting needs about 100,000 tokens in total, which is half of one model's free daily allowance.

## 9. What I'd do next

1. Re-run the 35-minute trap meeting once the daily token limit resets, and re-check the 13-minute meeting with the "postponing is not deciding" rule.
2. Measure `reasoning_effort="low"` for the documenter on the trap meetings. If classification holds, it would cut cut-offs and token use roughly in half.
3. Evaluate on real recordings (noise, crosstalk, accents) and compare FLAC vs Opus there.
4. Better speaker separation (e.g. pyannote) for segments where two people talk, and evaluation of voice grouping on real recordings.
5. Persist jobs (e.g. SQLite) so results survive a server restart.
