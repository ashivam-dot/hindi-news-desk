# Hindi news desk

An unattended, India-first desk that finds the stories India and the world are looking at and tells them as Hindi
YouTube Shorts: real Wikimedia Commons photos with a gentle depth-parallax camera, a Hindi script grounded in
Wikipedia and Wikidata, the Gemini TTS voice Sulafat, word-by-word Devanagari captions, and every number traced to a
named source. Derived from Orbitwire (`ashivam-dot/rebuilt-in-3d`), its English sister channel, whose stories it
does not duplicate. The binding editorial rules are in [CHANNEL.md](CHANNEL.md).

The channel's name and id are not set yet (`desk/config.py`); until `DESK_CHANNEL_ID` is set nothing can publish.

## How a Short is made

| Step | Module | What it does |
|---|---|---|
| Watch | `desk/trends.py`, `desk/news.py`, `desk/wiki.py` | Wikipedia most-read, Google Trends (IN, US, GB), Google News lead stories in English and Hindi (`hl=hi&gl=IN&ceid=IN:hi`), classified on Wikidata. Hindi headlines are matched on Hindi Wikipedia and mapped to English articles. |
| Desk | `desk/plan.py` | Ranks by fame decayed by age, India first; 08:00–23:00 IST, four an IST day, two hours apart, plus a breaking lane. |
| Orbitwire | `desk/orbitwire.py` | Reads Orbitwire's public `state` ledger; skips its stories unless high-profile, and gives those a new angle, other photos and a three-hour gap. Fails closed. |
| Script | `desk/writer.py`, `desk/gemini.py`, `desk/llm.py` | Gemini (free tier, ListModels discovery, the next model on a 429), then local Gemma 4, writes Hindi beats from English and Hindi Wikipedia plus Wikidata; number, `{hi, en}` name, Latin-word and decorum gates, then a bilingual fact-check pass. |
| Gate | `desk/gate.py`, `desk/hindi.py` | Devanagari-aware number normalisation (लाख, करोड़, Devanagari digits), Hindi and English banned words, casualty rule, free and credited photos, AI disclosure, Sulafat-only voice, Orbitwire rules. |
| Photos | `desk/media.py`, `desk/faces.py`, `desk/depth.py` | Freely licensed Commons photos, the subject's face matched across them, Depth Anything V2 for parallax. |
| Voice | `desk/voice.py`, `desk/align.py`, `tts/` | Gemini Sulafat; Whisper large-v3-turbo checks every Hindi line (coverage 0.75, three takes) and measures pace (140–155 wpm). Fallback: Chatterbox Multilingual cloning `tts/voices/sulafat_ref.wav`; otherwise hold. |
| Render | `desk/compose.py` | 1080×1920, 30 fps; RAQM-shaped Mukta captions, chips, credits, an always-on "AI आवाज़" label and a Hindi end card; music bed and −14 LUFS mix. |
| Publish | `desk/youtube.py` | Identity-pinned to the configured channel id; uploads private, waits for processing, then public, with the synthetic-content flag and a Hindi description. |
| Memory | `desk/ledger.py` | `published.json` (with `orbitwire_overlap`), `skipped.json`, `retries.json`, `candidates.json`, `health.json` on the `state` branch. |

## Running it

```
uv sync --extra dev
uv sync --project tts                                  # Chatterbox, for the fallback and --voice-preview
uv run python -m desk.cli watch                         # what's eligible right now (nothing saved)
uv run python -m desk.cli make "wiki:Article title"     # build, gate, voice and render one story into work/
uv run python -m desk.cli make "wiki:Article title" --voice-preview   # same, preview voice (never publishable)
uv run python -m desk.cli run --dry [--voice-preview]   # one pass that makes the best candidate, never publishes
uv run python -m desk.cli publish <story-id>
uv run pytest
```

## GitHub Actions

- `run.yml`: every 30 minutes (:22, :52); `workflow_dispatch` with `dry` (default on), `event`
  (`wiki:<title>`, make only) and `voice_preview`. Dry runs never publish or write the ledger; the MP4, stills and
  JSON records are kept as the `short-<run id>` artifact for 14 days.
- `health.yml`: every six hours; opens or updates an `alert` issue when the desk is silent, failing or holding.
- `reference.yml`: run once after `GEMINI_API_KEY` is set, to make and commit the Sulafat reference clip.
- `tests.yml`: the test suite on every push.
- Repository variable `PAUSED=true` stops the schedule and the health alerts.

What the coordinator supplies (environment `youtube` unless noted):

| Name | Kind | What it is |
|---|---|---|
| `GEMINI_API_KEY` | environment secret | Google AI Studio key (writer and Sulafat voice) |
| `YOUTUBE_OAUTH_JSON` | environment secret | authorized-user JSON for the channel (scope `youtube.upload` + `youtube`) |
| `DESK_CHANNEL_ID` | variable | the channel's `UC…` id; the uploader refuses any other channel |
| `DESK_CHANNEL_NAME`, `DESK_CHANNEL_NAME_HI`, `DESK_CHANNEL_HANDLE` | variables | shown on the end card and in tags |
| `PAUSED` | repository variable | `false` to start publishing |

## Data and credits

Facts: Wikipedia (CC BY-SA 4.0) and Wikidata (CC0). Photos: Wikimedia Commons, credited per file. Earthquake
magnitudes and alerts: U.S. Geological Survey (public domain). Font: Mukta (SIL Open Font License, `desk/fonts`).
Speech recognition: Whisper large-v3-turbo (MIT) via faster-whisper. Fallback voice engine: Chatterbox Multilingual
(MIT). Depth: Depth Anything V2 Small (Apache-2.0). Faces: OpenCV YuNet and SFace. Fallback writer: Gemma 4
(Apache-2.0) via llama.cpp (MIT). Narration: Google Gemini TTS, voice Sulafat.
