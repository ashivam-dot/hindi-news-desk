# Channel rules (binding for every Short)

The channel's name, handle and YouTube channel id are not decided yet: they live only in `desk/config.py`
(overridable by the repository variables `DESK_CHANNEL_NAME`, `DESK_CHANNEL_NAME_HI`, `DESK_CHANNEL_HANDLE` and
`DESK_CHANNEL_ID`). While `DESK_CHANNEL_ID` is `TBD` nothing can be published, and the uploader refuses every write
unless the signed-in channel's id equals it. The channel is a personal project: never a work account, work seat or
work key, and its browser work happens only in the owner's personal Chrome profile.

It is the Hindi sister of **Orbitwire** (`ashivam-dot/rebuilt-in-3d`, English). The two must not publish the same
story the same way (see "Orbitwire" below).

## What it is

The biggest stories India and the world are already looking at, told in Hindi as short documentaries: real photos of
the person or the event, a story with feeling, and facts checked against public sources. Hindi (Devanagari), 35–60
second vertical Shorts, YouTube category News & Politics, language `hi`.

A story qualifies only when people are already looking at it (Google News lead stories in Hindi and English for
India, the US and the world; Google Trends for India first, then the US and the UK; English Wikipedia's most-read
list; see `desk/news.py` and `desk/trends.py`) **and** it can be shown honestly:

- an incident at most 30 days old: flight incidents, storms, floods, wildfires, volcanoes, earthquakes, rail and
  maritime accidents, explosions, terror attacks, strikes in a war;
- a protest or public movement that at least two lead stories (English or Hindi) are about, that Wikidata does not
  mark as ended, and that began within two years. A months-old war is not ongoing news; only its new strikes and
  attacks qualify, as incidents;
- the death of a famous person, at most 10 days ago.

Sport, celebrity gossip, election results and crime trials are out of scope even when they trend.

## The editorial desk (`desk/plan.py`)

The desk is India-first and runs unattended; it decides what goes out and when.

- Priority is fame (Google News lead stories in English and Hindi, Google Trends traffic, Wikipedia views) halved
  every half-life (18 h for protests and quakes, 36 h for deaths), times 1.6 for an India story or 1.25 for a world
  story with an India link (Wikidata points at India, Indian newsrooms or searches lead with it, or Hindi newsrooms
  cover it). A fresh story beats a bigger stale one; a follow-up headline does not make an old incident fresh.
- **Timing is the channel (owner, 2026-10-10: "its all about the timing when the news or incidents are trending").**
  A Short goes out while people are looking at the story, as soon as it is made; a story is never held back until
  it has gone cold.
- A story more than 48 hours old is dropped unless it is trending live right now (Google Trends traffic, or a lead
  headline under 24 hours old). Wikipedia's most-read list is a day behind and never keeps an old story alive.
- Regular Shorts go out 07:00–24:00 IST, at most ten an IST day, at least 30 minutes apart.
- Breaking news (fame 400k+ and under 12 hours old, or an earthquake USGS rates magnitude 7+ or PAGER orange/red)
  goes out at any hour with no gap, up to two beyond the daily cap (`BREAKING_EXTRA`, set to 0 to make ten a hard
  cap). Wars never take the breaking lane.
- An ongoing story comes back at most once in 6 days, whatever its id.
- At most two loss stories in any three consecutive uploads.
- The run happens every 15 minutes (:07, :22, :37 and :52).

## Orbitwire (`desk/orbitwire.py`)

Before every run the desk reads Orbitwire's public ledger
(`https://raw.githubusercontent.com/ashivam-dot/rebuilt-in-3d/state/published.json` and `candidates.json`) and matches
stories on the Wikidata QID in their `wk-<QID>` ids (suffixes such as `-2026w41` or `-p2` included).

- A story is **shared** when Orbitwire published or scheduled that QID within the last 7 days, or it is Orbitwire's
  current top candidate.
- A shared story is skipped unless it is **high-profile**: fame 400k+, or the top 10% of this run's candidates with at
  least 100k, or an India story that at least three Hindi lead headlines are about.
- A high-profile shared story is told differently: its own angle (India connection when it has one; otherwise a
  timeline for a death, an explainer for an incident or protest), a Hindi hook and a title that shows the angle,
  and photos Orbitwire would not use (Orbitwire's own deterministic photo ranking is recomputed with a margin and
  every file in it is excluded; extra photos come from a Commons search). It goes out at least three hours after
  Orbitwire's release, and never while the story is only Orbitwire's top candidate.
- If Orbitwire's ledger cannot be read, the desk publishes nothing that run (it cannot tell what it would duplicate).
  The check is repeated just before upload.
- Every ledger row records `orbitwire_overlap` (null, or the QID, Orbitwire's status, id and release time, why the
  story was high-profile, and the angle used).

## How a Short looks

- **Pictures:** at least three real, freely licensed photos from Wikimedia Commons (CC0, public domain, CC BY,
  CC BY-SA; never non-commercial or fair-use files), each credited by author and licence on screen (`फ़ोटो: author /
  licence / Wikimedia Commons`) and in the description. For a person, every photo must show them: their face is
  matched across the set. A gentle depth-parallax camera move brings each still to life; nothing in a photo is
  invented or altered.
- **Never** generate a realistic image or video of a real person or a real incident.
- **Story, not a résumé:** a hook that says plainly what happened; then where they began, the turning point, the work
  people loved (named, with years on screen), a human detail, and what they leave behind. On-screen chips name works,
  roles, honours or years, never places.
- **Hindi on screen:** Devanagari is shaped with HarfBuzz (Pillow's RAQM layout) in Mukta (OFL, bundled). Rendering
  refuses to run without RAQM, because basic layout breaks conjuncts and vowel signs. Captions appear word by word on
  Whisper's timings and always show the script's own words.
- **Voice:** one voice only, Gemini TTS **Sulafat** (female): a warm, clear, expressive Hindi storyteller, never
  sensational, at 140–155 Hindi words a minute measured from Whisper's word timings (a take a little off pace is
  re-timed with pitch kept). Whisper large-v3-turbo listens to every take in Hindi; every line must reach 75% of its
  letters heard, the take may not add speech, and three failed takes reject the narration. When no Gemini TTS model
  can read, the fallback keeps the same voice: Chatterbox Multilingual clones `tts/voices/sulafat_ref.wav`, a
  reference clip made once from Gemini Sulafat by `tools/make_reference.py`. Without that clip the run holds. There
  is never a fallback to a different voice or gender. `--voice-preview` (dry runs only) uses Chatterbox's built-in
  voice to test the pipeline; such a Short is marked and can never be published.
- **Writer:** Gemini (free tier, models discovered at run time, the next model on a 429) and the local Gemma 4 model
  when Gemini cannot answer. Sources: English Wikipedia, Hindi Wikipedia when it has the article, Wikidata's Hindi
  labels, and confirmed Wikidata facts.

## Editorial standards

- Every number on screen or in the narration has its value in a named public source listed in the description:
  Devanagari digits and Indian scale words are normalised (15 लाख = 1,500,000; a million is 10 लाख; a scaled amount
  may round its source by 1%). `gate.py` and the writer enforce this mechanically. A death toll is said only when
  Wikipedia's infobox and Wikidata agree on it; without one, an incident never speaks of casualties.
- Every proper noun is listed as a `{hi, en}` pair: the English must be in the English source (or the Hindi in the
  Hindi source), the Hindi must be in the script, and Wikidata's Hindi label wins when there is one. Latin-script
  words must be in the English source. Pairs whose spellings are far apart go to the second, bilingual fact-check
  pass, which lists anything unsupported.
- Decorum (Hindi and English): no victims, bodies or injuries shown or described in detail; no gore, sensational or
  clickbait words (ब्रेकिंग, बड़ी खबर, सनसनीखेज, चौंकाने वाला, खौफनाक, दिल दहला देने वाला and the rest of
  `gate.BANNED`); no emoji; no all-caps titles; no requests to like, share or subscribe. Loss is stated plainly with
  official figures, in respectful Hindi (नहीं रहे, का निधन).
- Attacks: never name or show the attacker, never describe weapons or methods. Deaths: never speculate on a cause;
  suicide is never mentioned. Protests are strictly neutral, every disputed claim attributed (पुलिस के मुताबिक,
  आयोजकों के अनुसार); the script never urges anyone to join or avoid a protest and never mocks or praises a person,
  party, community or religion.
- **AI labelling (India's IT Rules, 2026, and YouTube):** every frame carries a visible "AI आवाज़" label; the end card
  says "असली तस्वीरें: Wikimedia Commons · आवाज़: AI"; the description says in Hindi that the voice is AI and which
  engine read it; every upload sets YouTube's altered-or-synthetic-content flag.
- Corrections: a wrong fact is fixed in the description and pinned comment the same day; a wrong number on screen
  means the Short is made private and re-made.

## Operations

- The half-hourly GitHub Actions run (`run.yml`) is the only automatic publisher. Its state lives on the `state`
  branch. The repository variable `PAUSED=true` holds the schedule and the health alerts; manual dry runs still work,
  and a manual run that would publish refuses while paused.
- Secrets live only in the GitHub environment `youtube`: `GEMINI_API_KEY` and `YOUTUBE_OAUTH_JSON`. The key travels
  only in a request header and is never logged or written to disk.
- An open issue labelled `alert` means the desk needs attention (a failed run, four hours of silence, or a hold such
  as no Sulafat voice); GitHub emails the repo owner.
- Never promise views or earnings; growth comes from accuracy, consistency and clarity.
