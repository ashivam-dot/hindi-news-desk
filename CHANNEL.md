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
list; the story articles Wikipedia's editors list on today's and yesterday's Current events page, each counting like
two lead headlines, an India story when listed under an India topic; see `desk/news.py` and `desk/trends.py`)
**and** it can be shown honestly:

- an incident at most 30 days old: flight incidents, storms, floods, wildfires, volcanoes, earthquakes, rail and
  maritime accidents, explosions, terror attacks, strikes in a war;
- a protest or public movement that at least two lead stories (English or Hindi) are about, that Wikidata does not
  mark as ended, and that began within two years. A months-old war is not ongoing news; only its new strikes and
  attacks qualify, as incidents;
- the death of a famous person, at most 10 days ago.

Sport, celebrity gossip, election results and crime trials are out of scope even when they trend.

**India explainers (2026-10-13; owner: "active most with high rated topics, most popular topics, trending topics";
"each and everything should be based on full real authorised facts").** `desk/explain.py` adds the day's biggest
Indian stories that are not incidents or deaths: politics, policy, the economy, diplomacy, defence, the courts'
public rulings, science and the weather (`kh-<IST yyyymmdd>-<centre's QID>`). One qualifies when at least 3
independent owners' English headlines within 24 hours tell the same story (grouped only when most of its headlines
match, never by an institution or a big place alone), its centre (the person or institution most headlines name, by
full name) has a Wikipedia article and Wikidata item, and it is about India. Elections and campaigns, sport,
entertainment, gossip, crime, arrests, raids, bail and trials, communal violence, deaths and attacks, protests (their
own lane), market tips, roundups, opinion and live blogs never qualify; nor do dead people, people convicted of crimes,
disambiguation pages or whole countries as a centre. Fame is one lead headline per independent owner (English and
Hindi outlets, at most 8) plus Google News India lead stories naming the centre (at most 8); an explainer never takes
the breaking lane, halves every 14 h, and one centre is explained at most once in 20 h. What happened and why comes
only from at least two independent owners' articles (the writer's checks and the gate, as for every Short); a
headline is context, never a source; the centre's Wikipedia article is background only. Sentences about deaths,
injuries, suicide, suspects and arrests are removed from the articles. The Short is strictly neutral: every claim,
allegation and reason attributed to whoever made it, each side as reported, no motives guessed, no predictions, no
financial, legal or medical advice; when no report gives a reason it says so. Its title may ask the story's own
question ("... ने इस्तीफ़ा क्यों दिया?"). Photos are the centre's own Commons photos (a person's face-matched portraits).
A centre must be the subject of its article: a search for "<name> of India" counts only when the title is exactly
that (or "<name> (India)"), or the name is the article's acronym (UPI, RBI); never "Greece–India relations" for a
story about Greece.

**Independent owners, across every lane (2026-10-13).** Wire copy is one owner, whoever prints it: an article
crediting PTI, ANI, IANS, UNI, Reuters, AFP or AP (or भाषा) counts as that agency, and two articles whose text is
mostly the same count once (`desk/outlets.py`, `wire`). Photo descriptions are never given to the writer as facts.
The lane is behind the repository variable `DESK_EXPLAINERS=true`; with it off the radar still finds and records
explainers (`explainers` in `state/candidates.json` and a note per run), and a manual dry run can turn it on for that
run only (`explainers` input).

**Fresh articles (2026-10-11; owner: "its a news channel it should be active most").** A brand-new event article often
has no Wikidata item for its first day, exactly while the story is hottest. It still qualifies when its English title
names this or last year and an incident or protest shape, the way Wikipedia titles events ("2026 Erie shooting",
"2026 anti-CEC protests"; riots, trials, elections and sport never). Its date comes from the infobox, its location
photos from the places the infobox links to (target, location, site; each place's main image plus up to 3 photos from
its own article whose file name names it, never a map and never one that features a person's face, since that would
pass them off as part of the story), its id is `wp-<article title>` (so it never comes back as `wk-<QID>` once
Wikidata catches up), and with no Wikidata to agree with, no casualty number is ever said.

**Story supply (2026-10-13).** A young article waits: "under 6 hours old" never counts as a try (six tries, at a run
about every 30 minutes, gave every fresh article up before it was 6 hours old), and a story once given up only for
that comes back. Wikipedia's search ranks long-standing articles above a brand-new one, so headlines and Google
Trends news items are also matched by their words to a pool of fresh stories: people Wikidata says died in the last
10 days, and event articles created in the last 48 hours or listed on Current events (a person by their whole name
in order, an event by its place or name plus one more title word, a Hindi headline by the item's Hindi label; a
headline two items fit matches nothing). Any search Google Trends lists counts (traffic 100+). The most-read list is
read 1000 deep for those deaths and fresh events. A GDACS Orange or Red alert from the last 4 days leads to its
disaster's own article (`desk/gdacs.py`; worth 50k or 150k fame), and Google News' Hindi world section is read too.

**Trusted sources beyond Wikipedia (2026-10-13; owner: "don't relay on wikipedia only search for other trusted souces
as well").** `desk/outlets.py` keeps an allowlist of trusted outlets with public RSS feeds: official (PIB in English
and Hindi, UN News Hindi), public broadcasters (BBC World, BBC India, BBC Hindi, DW, NPR, France 24), international
(Al Jazeera, The Guardian), Indian national (The Hindu, Hindustan Times, Times of India, NDTV) and Hindi (Live
Hindustan, Amar Ujala, AajTak, ABP Live, NDTV India). Added 2026-10-13 for the explainers (feed read and article
text extracted): The Indian Express (India, business), News18, India Today, Mint (news, economy), The Economic Times,
The Hindu (business, sci-tech), Dainik Bhaskar, News18 Hindi, Zee News and TV9 Bharatvarsh. Each outlet has an
`owner`; sister brands count once (HT Media is Hindustan Times, Live Hindustan and Mint, the BBC is all three BBC
feeds, the Government of India both PIB feeds, NDTV both NDTV feeds, Bennett, Coleman & Co. the Times of India and
The Economic Times, Network18 both News18 feeds, the India Today Group AajTak and India Today). PIB, NDTV and France 24 get a browser's request headers (they refuse others with 403); a headless
browser (Crawl4AI) was benchmarked on 2026-10-13 and read nothing more, with noisier text. Feeds are read in parallel once a
run (36 hours back); a feed that fails is listed in the run's errors and the rest still count. Articles are read
with trafilatura (20 s timeout, at most 12 a run, cached). Outlet photos are never used. Plain-http links are read
as https.
- **Discovery:** outlet headlines join Google News: matched to a Wikipedia article the same way, each independent
  owner adding one lead headline's fame (at most 6), and a Hindi outlet's headline counting as a Hindi headline.
  Only national sections count as an India signal; a feed that mixes India and world news (Times of India top
  stories, Amar Ujala breaking, AajTak and ABP Live home) never makes a story an India story.
- **Corroboration:** the writer gets a REPORTING block of 2-4 articles about the story (named by its headline or
  summary, inside its time window), each from a different owner, official, public and international ones first; a
  report found at discovery is used only if it names the story. Every number, name and claim must be in
  Wikipedia/Wikidata or in the articles of at least two independent owners; one outlet alone never backs a fact (the
  writer's checks and `desk/gate.py` both refuse it). A casualty number still needs the infobox and Wikidata to
  agree, or else two owners stating the same exact number (no hedge before or after it, such as "at least", "or
  more" or "से अधिक"; no other number from any outlet; never a number different from the infobox's; and Wikidata
  agreeing when it has one), or one owner and Wikidata's only toll. The toll reaches the writer as a confirmed fact:
  every sentence about deaths, bodies or injuries is removed from the articles, as are sentences about suicide and,
  for an incident, any naming a suspect, attacker or arrest.
- **Stories Wikipedia has no article for yet** (`nw-<yyyymmdd>-<place>-<kind>`): at least 3 independent owners
   within 24 hours, one of them official, a public broadcaster or international (or 4 owners of any group), whose English headlines name the
  same incident or protest (same scope rules; sport, politics, trials and gossip never). They are told only from
  the reporting (at least two owners' articles must name the place), with photos of the place (Commons, then
  Openverse; the place must be a Wikidata item with coordinates, never a person). Once Wikipedia writes the article,
  the story is
  not told again for 7 days (a shared report URL, the same nw- place and kind, or its headlines naming the article),
  and Orbitwire's overlap rules match nw- ids and report URLs too. **The lane is on (2026-10-13)** through the
  repository variable `DESK_NEW_STORIES=true`, passed into the run job's `env` in `.github/workflows/run.yml`. Set the
  variable to anything else to turn it off: the radar then still finds and logs these stories ("emerging" in
  `state/trends.json`, counted in the run's outlets note) but does not offer them.
- **Photos:** when Commons has fewer than 3 usable photos, Openverse (keyless; CC0, CC BY and CC BY-SA only, never
  non-commercial, no-derivatives or the public-domain mark) fills in with photos of the places the story links to
  (Wikidata items with coordinates; never a person, group or work), never one that features a face; each is
  credited to its author, licence and host.
- **Description:** "स्रोत: Wikipedia, BBC, The Hindu" names the outlets behind the facts, then every URL. When it
  would pass YouTube's 5,000 bytes (eight photo credits with long Commons URLs did, 2026-10-14), the narration
  paragraph goes first, then the photo credits are grouped by licence; the sources and AI disclosure always stay.
- **A person's photos:** their own portraits come before photos where other prominent faces stand beside them, so
  strangers are not shown as part of today's story.
- **Explainers give the other side:** when one side acts against another, the response REPORTING carries, attributed,
  or one line saying the reports carry none; English idioms are said as a Hindi bulletin would ("high tea" is
  "चाय पर बैठक").

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
- Regular Shorts go out 07:00–24:00 IST, at most twenty an IST day, at least 20 minutes apart (2026-10-14; owner:
  the news channels must be the most active, because they live on incidents and news; ten a day and 30 minutes left
  stories untold).
- **The news lane (`desk/explain.py`, kh- ids, 2026-10-14).** Any story at least three independent owners report
  within 24 hours qualifies, whatever its topic, unless it is on the skip list (elections, sport, entertainment,
  gossip, crime and trials, communal violence, market tips, opinion, roundups); a headline with no special category
  is `समाचार`. Its centre may be Indian or from anywhere in the world (a world centre is told as a world story).
  Common Indian institutions resolve straight to their articles (`ALIASES`: Indian Railways, RBI, Supreme Court of
  India, DGCA, ...); a festival, holiday, people, country, language or religion is never a centre. Up to 25 lookups a
  run, two centre names tried per story. The 14 Oct analysis found 37 stories with 3+ owners in 24 h while the old
  India-only, special-topic lane produced one or two.
- Breaking news (under 12 hours old with fame 400k+, or an incident five independent outlets report, two of them
  official, public or international; or an earthquake USGS rates magnitude 7+ or PAGER orange/red) goes out at any
  hour with no gap, up to two beyond the daily cap (`BREAKING_EXTRA`, set to 0 to make ten a hard cap). Wars and
  ongoing protests never take the breaking lane.
- **Big incidents are told while they happen (2026-10-14; owner: "these two channels should be fully active and
  publishing the videos as a big incident happen").** A Wikipedia article under 6 hours old is still not used (its
  facts move), but when at least three independent outlets, one of them official, public or international, already
  report the incident, it is told at once from that reporting, exactly as an nw- story (two owners for every fact,
  no toll unless the reports agree on it). The published record keeps the article's title, so the story is not told
  again from Wikipedia later.
- An ongoing story comes back at most once in 6 days, whatever its id.
- **What the Hindi audience watches (2026-10-18; owner: "no body is watching those, i told you to pick famous and
  trending topics").** The channel's own numbers: Nana Patekar's death 1,301 views, Rahul Gandhi vs the MEA 554,
  Delhi metro closures 330, actor Imran Khan told to leave India 321; White House, Pope and Starlink statements 0-35;
  every follow-up part 4-8. Meanwhile the biggest Indian stories were lost to the desk's own rules: Abhijeet Dipke's
  detention led Google News India for four days and failed 21 times on "1 photo (want 2)", and the Kolkata pandal
  stampede (19 dead) never became a candidate. So:
  - an explainer must be in Google News India's top stories (its headline-count fame never makes it "famous"), and a
    world explainer must be in the Hindi lists (IN-hi, IN-hi-nation);
  - follow-up parts are off (`plan.SERIES_PARTS = 1`);
  - a kh- story about a person shows only that person's own photos (never their school or birthplace: the Dhruv
    Rathee Short was seven frames of buildings), and one photo is enough when it is a lead story (place 0.9+);
  - an nw- story stands on 4 independent owners of any group (or 3 with an official, public or international one);
    collapses (pandal, building, chimney...) are incidents; only an article a story can be told from (a candidate
    or an event-shaped title, never "List of fatal crowd crushes") holds its headlines back; ties in an nw- name go
    to the name the headlines write first ("Kolkata Durga Puja pandal");
  - a month or a date is never a centre ("October" from Delhi traffic headlines would have led the morning).
- At most two loss stories in any three consecutive uploads.
- The run happens every 15 minutes (:07, :22, :37 and :52).

## Orbitwire (`desk/orbitwire.py`)

Before every run the desk reads Orbitwire's public ledger
(`https://raw.githubusercontent.com/ashivam-dot/rebuilt-in-3d/state/published.json` and `candidates.json`) and matches
stories on the Wikidata QID in their `wk-<QID>` ids (suffixes such as `-2026w41` or `-p2` included), and a story
told before Wikidata knew it on its `wp-<article title>` id or the article Orbitwire recorded.

- A story is **shared** when Orbitwire published or scheduled that QID within the last 7 days. Orbitwire's top
  candidate is not a release and never holds a story (2026-10-14: holding for it left the Multan derailment untold
  on both channels).
- A shared story is skipped unless it is **high-profile**: fame 400k+, or the top 10% of this run's candidates with at
  least 100k, or an India story that at least three Hindi lead headlines are about, or any India story with fame 25k+
  (Hindi viewers are not Orbitwire's English audience; 2026-10-11, after Nana Patekar's death was skipped).
- A high-profile shared story is told differently: its own angle (India connection when it has one; otherwise a
  timeline for a death, an explainer for an incident or protest), a Hindi hook and a title that shows the angle,
  and photos Orbitwire would not use (Orbitwire's own deterministic photo ranking is recomputed with a margin and
  every file in it is excluded; extra photos come from a Commons search). It goes out at least three hours after
  Orbitwire's release.
- If Orbitwire's ledger cannot be read, the desk publishes nothing that run (it cannot tell what it would duplicate).
  The check is repeated just before upload.
- Every ledger row records `orbitwire_overlap` (null, or the QID, Orbitwire's status, id and release time, why the
  story was high-profile, and the angle used).

## How a Short looks

- **A TV news bulletin, not a slideshow (owner, 2026-10-14: "it really doesn't look like a news report, no facts
  nothing is shown").** Every Short uses the bulletin template (`compose.render_bulletin`): a top bar with the
  category in red, the channel name, `ताज़ा` for today's news and the date; the photo in a framed window marked
  `फ़ाइल फ़ोटो` with its credit; a headline bar under it with the declarative headline and `स्रोत:` the outlets; a
  fact card for every beat (the sourced number or decision large, a label saying what it is, and the outlets whose
  reports state that number); subtitles; a `मुख्य तथ्य` ticker of the facts along the bottom; and a `मुख्य तथ्य`
  recap on the end card. Every word on screen is the gated title, a gated card or the narration.
- **Pictures:** at least three real (two for kh- and nw- bulletins, where the cards carry the frame), freely licensed photos from Wikimedia Commons (CC0, public domain, CC BY,
  CC BY-SA; never non-commercial or fair-use files), each credited by author and licence on screen (`फ़ोटो: author /
  licence / Wikimedia Commons`) and in the description. For a person, every photo of a person must show them: their
  face is matched across the set. A story with fewer than three photos of its own (a tribute needs at least one
  matched photo of its subject) is filled with photos of the places and things it links to: a person's birthplace,
  school, employer, team or award, an incident's places. A fill photo never features a face. A gentle
  depth-parallax camera move brings each still to life; nothing in a photo is invented or altered.
- **Never** generate a realistic image or video of a real person or a real incident.
- **Backgrounds follow the topic (owner, 2026-10-10: a single background "looks very basic").** Nothing goes out on
  one plain backdrop. Public-service advisories (`desk/advisory.py`, `advisories/*.json`) name a real Commons photo
  for every beat (the closed station, the terminus, the road under diversion); it fills the frame with the parallax
  camera move, the card sits on frosted glass over it and unrolls line by line, and every photo is credited on screen
  and in the description.
- **A formal news report (owner, 2026-10-14: the delivery "is really very casual").** The writer is a news editor
  writing for an anchor: a lead sentence with who, what, where and the key number; the details with attribution;
  the official statement; क्यों (or that no official reason was given); the other side; आगे क्या. Third person, no
  viewer address (आइए, दोस्तों, जानिए), no exclamation, no rhetorical question, no question title, no biography
  padding, no moral or conclusion; `writer.casual` rejects a draft that slips. A death is a news obituary report.
  Cards carry the key fact (a number with its unit whenever the beat has one) and a label, never a place alone.
- **Engaging and visibly sourced (owner, 2026-10-13: "more attractive news ... 100% engaging ... real facts").**
  Every frame carries the channel strip (`क्यों हुआ · राजनीति`, the story's kind or explainer category) and a thin
  progress bar along the top edge; the opening shot names where the facts come from (`स्रोत: बीबीसी · द हिंदू ·
  Wikipedia`). The script's first five words carry the news (never a date, a question or a slow introduction),
  every beat adds one new sourced fact, and the last beat is a short factual sentence. Engagement never comes from
  hype: the banned-wording list and every fact check still apply.
- **Hindi on screen:** Devanagari is shaped with HarfBuzz (Pillow's RAQM layout) in Mukta (OFL, bundled). Rendering
  refuses to run without RAQM, because basic layout breaks conjuncts and vowel signs. Captions appear word by word on
  Whisper's timings and always show the script's own words.
- **Voice:** one voice only, Gemini TTS **Sulafat** (female), directed as a senior Hindi TV news anchor: formal,
  crisp, authoritative and measured, never conversational or sensational, at 128–148 Hindi words a minute measured
  from Whisper's word timings. `gemini-3.8-flash-lite-tts` reads first (owner, 2026-10-14: the 10 Oct voice was
  better; that Short was read by flash-lite, the later ones by flash). (A take a little off pace is
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
