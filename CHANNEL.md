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
  the reporting (at least two owners' articles must name the place), with photos of the scene first (Commons files
  naming the place and the words half the headlines share: "Kolkata Durga Puja pandal", never a city postcard when the
  scene has photos), then of the place (Commons, then
  Openverse; the place must be a Wikidata item with coordinates, never a person). A title may state a cause ("... बनी
  वजह") only with who gives it ("... के मुताबिक"). Once Wikipedia writes the article,
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
- **Only the big stories, told properly and on time (owner, 2026-10-21: "No need to cover each and every incidents
  but those which are really high profile cases or incidents those should be cover properly on time with max
  efforts").** Regular Shorts go out 07:00–24:00 IST, at most six an IST day (`plan.MAX_PER_DAY`), at least 20
  minutes apart; breaking news and a case's angles may take two more (`BREAKING_EXTRA`). The cap counts the Shorts
  still on the channel (`plan.on_channel`): a retired Short frees its slot and a Short and its remake count once (on
  21 Oct every run from 13:12 IST held "already 8 Shorts today" with three of the eight private). Before 18:00 IST
  the regular lane and case angles stop at four (`EVENING_RESERVE`), so two slots wait for the evening; breaking
  news is never held for it. Case angles are held too on purpose: they count toward the same four, and if they
  could fill the day before 18:00 the evening would again find the cap used up. Every story must be high in
  Google News India's top stories (`MIN_PLACE`, about the top 13), and a kind Hindi viewers rarely watch
  (`plan.DEMAND` under 0.8: protests, science, conflict, economy, diplomacy, world) about the top 6. The ranking is
  multiplied by `plan.DEMAND`: crime and security interest 84% of Hindi news users and entertainment 75%, business
  38% (Google/Kantar 2023); on this channel a star's death drew 1,301 views and economy, diplomacy and world
  explainers 10-60. Half a news video's first-day views come in its first 6-7 hours, so a big story must be out
  within hours: the Tiger Shroff firing was missed for 13.5 hours because "shot", "gunned down" and "murdered"
  headlines were not seen as incidents and sport words skipped a firing at a football ground (`outlets.py`, fixed).
- **Ad-safe topic mix (2026-10-22, for YouTube's Partner Programme).** The ranking is also multiplied by
  `plan.ad_factor`: x0.8 (`AD_SENSITIVE`) for crime, shootings, firing, arrests, bail, courts, communal or religious
  flashpoints and accidents, x1.2 (`AD_FRIENDLY`) for economy and prices (petrol, gold, GST, RBI, EMI, tax), jobs,
  exams and schemes, telecom and tech rules, infrastructure, science and neutral diplomacy. A keyword classifier
  (`plan.ad_class`) reads the title, story and English and Hindi headlines (a Hindi word must start a word, so
  "सोना" is not "सोनाक्षी", and a longer word that is another word is no match: दौरान is no दौरा, दामाद no दाम,
  नियमित no नियम, "दिल का दौरा" no visit); English words that fit any story need a pairing word (a state visit, trade
  talks, a price hike, a rail project; not "Kohli talks" or "visits hospital"), and a market crash is no accident.
  Sensitive wins when both match, an obituary is sensitive only through such words, and "cardiac
  arrest" is no arrest. It is a multiplier, never a ban, and breaking news is exempt. One health line
  (`plan.ad_note`) names the stories it moved. Honest trade-off: on this channel attack (median 85 views, 13 Shorts)
  and court (112, 6) outdrew economy (29, 5), so this costs some views for advertiser suitability; it stays mild.
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
  hour with no gap, up to two beyond the daily cap of six (`BREAKING_EXTRA`; YouTube refuses this channel's uploads past about ten a
  day, so `plan.YOUTUBE_DAILY_UPLOADS` bounds every upload, retired ones included, and the regular and case lanes
  stop two uploads short of it, so however many Shorts were retired the last two uploads of the day stay free for
  breaking news; the margin also covers YouTube counting a different day from the desk's IST day). Wars and
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
  - follow-up parts were off from 2026-10-18 (every part 2 drew 4-8 views) and are back on from 2026-10-20 (owner:
    "this tiger shrof case is in very lime light you can cover multiple sories of it with facts"): a story Google
    News India leads with (`plan.SERIES_SCORE`) gets up to `plan.SERIES_PARTS` Shorts in all, `plan.SERIES_GAP`
    apart, each from at least two owners' reports no earlier version used, kh- and nw- stories alike;
  - a case the whole country is following gets a case file (`cases/*.json`): one Short per angle (the family's
    response, the industry's, the probe, the government's, the scene), each from reports chosen for that angle,
    ahead of the other ready stories and inside the daily cap and the 20-minute gap. A case Short names only the
    people, places and bodies its file lists (`writer.off_case`): an accused is never named, only how many, where
    they are from, where they were caught and what police say. The file's `never` list (an accused's or a gang's
    name, in English and Hindi) may not appear anywhere in the script, and headlines carrying one are dropped. Its
    `status` says where the case stands now (an angle's reports may predate the arrests: the first dry run said
    police were still searching, a day after all three were caught), and no angle may contradict it. Each
    angle's `words` keep its people's sentences in the report excerpts. The file keeps the story's radar candidate,
    so the angles keep coming until its `until` after the story leaves the radar. Angles go ahead of other
    stories but at least 30 minutes apart (`CASE_GAP`), so the day's other news still runs between them, and an
    open case's story gets no separate follow-up parts. At most three of a case's angles go out an IST day
    (`plan.CASE_MAX_PER_DAY`) and six stay on the channel in all (`CASE_MAX_TOTAL`; retired and replaced Shorts do
    not count, and an angle made again is never over the total); the other angles wait with a "hold" note (review,
    2026-10-21: eleven angles on one case, one template, read as mass-produced). An angle may take the day's spare
    (breaking) slots, still within 07:00-24:00 IST and MIN_GAP after the last Short (owner, 2026-10-20: "publish
    few more"). An angle keyed `<key>-r2` with `replaces` (the old Short's YouTube id) makes that angle again and makes the old Short
    private once the new one is public (the family Short that called Jackie Shroff "जय किशन"). A gang may be named
    only as police or the reports attribute it ("पुलिस ... गैंग से जुड़े होने की जांच कर रही है"), never as fact, and
    only when the file lists it in `names_ok`; an accused or gangster by name stays in `never`;
  - a kh- story about a person never fills with their school or birthplace (the Dhruv Rathee Short was seven frames
    of buildings); its pictures are the person (a Commons search, not only their article), the other people and
    the places the script names (see "Every beat shows what it names" below). One photo of the subject is accepted
    for a lead story (place 0.9+) only because the beats bring the rest;
  - an nw- story stands on 4 independent owners of any group (or 3 with an official, public or international one);
    collapses (pandal, building, chimney...) are incidents; only an article a story can be told from (a candidate
    or an event-shaped title, never "List of fatal crowd crushes") holds its headlines back; ties in an nw- name go
    to the name the headlines write first ("Kolkata Durga Puja pandal");
  - a month or a date is never a centre ("October" from Delhi traffic headlines would have led the morning).
- At most two loss stories in any three consecutive uploads.
- The run is scheduled every 15 minutes (:07, :22, :37 and :52), but GitHub Actions starts scheduled runs late:
  on 21 Oct 2026 they started about 40 minutes apart (10:37, 11:17 ... 17:34, 18:07 UTC), so a made story can wait
  that long for the next run.
- **The channel's own numbers steer the ranking (`desk/learn.py`).** Every 3 hours a run reads each Short's views
  and scores it by its views at 24 h; a category or region with at least four scored Shorts gets a lift, shrunk
  toward 1 and kept within 0.75-1.35, that multiplies its stories' priority (`state/performance.json`,
  `state/LEARNINGS.md`). A video record that carries `avg_view_pct` (YouTube Analytics' average percentage viewed)
  adds retention, shrunk the same way and blended in at half weight. `learn.read_retention` fills it and
  `engaged_views` from YouTube Analytics v2 (`dimensions=video`, `metrics=views,engagedViews,averageViewPercentage,
  averageViewDuration,subscribersGained,likes,shares`) through the desk's own sign-in, only for Shorts at least
  three days old (the numbers settle about two days after); the same query stores the scorecard's gating numbers
  (`plays` from Analytics' views, `avg_view_s`, `subscribers_gained`, `likes`, `shares`). A metric the report
  refuses (HTTP 400) is dropped alone (the one the error message names, else the last one) and listed in
  `analytics_dropped`; views and average percentage viewed are never dropped. `learn.read_traffic` then reads where
  each Short's views came from (`dimensions=insightTrafficSourceType`, one query a Short) into `traffic`: at most
  30 Shorts a run, three to 28 days old, each at most once a day, never-read first.
  Analytics counts US Pacific days, so the window opens the UTC day before the oldest Short and ends three days
  back, before the days still settling.
  It needs the `yt-analytics.readonly` scope: without it (HTTP 403, or a token that lists its scopes without it)
  nothing is filled and one health note says so; lifts are then views alone.

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
- **A shared story needs an India connection (`orbitwire.MIRROR_NEEDS_INDIA`, 2026-10-22).** Even a high-profile
  shared story is told again in Hindi only when it is an India story, Wikidata or the newsrooms link it to India, or
  its headlines name India, an Indian place, Modi, Jaishankar or the MEA (`orbitwire.india_connection`; "Indiana" is
  not India); otherwise it is skipped with a note. A Hindi retelling of the English channel's world story is the
  mirroring YouTube's inauthentic-content policy is about, and Hindi viewers come for the India side. The constant
  is the switch: `False` tells the high-profile shared stories again as before, each with its own angle (a world
  story with no India connection never gets the India angle, so no ungrounded India line is asked for). World stories Orbitwire did not
  tell are not affected (world Shorts drew a median of 48 views, 29 Shorts, against 53 for India's 41).
- A high-profile shared story is told differently: its own angle (India connection when it has one; otherwise a
  timeline for a death, an explainer for an incident or protest; a world story India is part of takes the India
  angle), a Hindi hook and a title that shows the angle,
  and photos Orbitwire would not use (Orbitwire's own deterministic photo ranking is recomputed with a margin and
  every file in it is excluded; extra photos come from a Commons search). It goes out at least three hours after
  Orbitwire's release.
- If Orbitwire's ledger cannot be read, the desk publishes nothing that run (it cannot tell what it would duplicate).
  The check is repeated just before upload.
- Every ledger row records `orbitwire_overlap` (null, or the QID, Orbitwire's status, id and release time, why the
  story was high-profile, and the angle used).

## How a Short looks

- **Full screen, about 30 seconds (owner, 2026-10-21: "My main issue is you are not able to present the video
  properly").** Every story Short uses the full template (`compose.render_full`, `scene.template = "full"`), as BBC
  Hindi, DW Hindi, AJ+ and Aaj Tak's Shorts do: the picture fills the 9:16 frame (a portrait OSM map, a person's
  face kept in the upper part, a landscape photo fitted over its own blur) under a top and bottom darkening; a hook
  card for the first 3.6 s (`scene.hook`, or the first beat's card); a red name strap the first time each person
  appears (after the hook); when a beat names two people who both have portraits (Tiger and Jackie Shroff), a
  top/bottom split with a gold line; a pop-up fact chip (the number or decision and its label) for 3 s of each beat;
  the place stamp only over a map or a place's photo; large captions (84 px) at 72% of the height, above YouTube's
  title and buttons; the channel strip top left and the AI badge top right; a thin progress bar; a crossfade
  between pictures; and a 1.2 s end card (logo, follow, disclosure) after the last word, with no spoken outro. The
  half-screen bulletin (framed photo, headline bar, ticker, recap card) packed four layers of text over a small
  picture and is no longer used for stories. Scripts are 60-80 words in 6-7 beats (`writer.WORDS_ASKED`, gated
  52-82, at most 18 words a beat, no "आगे की कार्रवाई जारी है" ending: `writer.VAGUE`; the first dry run passed
  90 words in five 18-word beats and ran 40 s): Shorts of 15-30 s get 14% more views than a 10K-100K channel's median and those over 60 s fewer
  (TrendReport, 3.48M Shorts), and the 45-50 s Shorts were padded with biography and "no response" lines. Every word
  on screen is the gated title, a gated card or the narration.
- **Every beat shows what it names (owner, 2026-10-20, furious: the Tiger Shroff Short told the whole story over
  one photo; "how audience will stay to see this").** Read this before building or changing any Short:
  - never one picture for a whole Short: at least three distinct pictures (`visuals.MIN_VISUALS`, gated), and the
    picture changes every 3-4 seconds (a beat longer than `compose.CUT_AFTER` cuts at a word boundary);
  - each beat shows the person or place it names: that person's own portrait with a red name pill, an
    OpenStreetMap map of the place (`नक्शा`, credited), a route map when it names two places, the police of the
    city whose police the script names (Mumbai Police, not the first home district's) for a police beat (an Indian
    story only: a case file sets `region`, as the radar called the Tiger story "world" and the police photos were
    skipped), and for a landmark (a station, a hospital, a beach: a place with no population) its own Commons
    photo before its map; up to seven towns and landmarks plus three states, and a police force is never a place
    (the probe's states, then "Kota Police", filled the places and Kota's station, where all three were caught,
    went out over a portrait); a case file lists every spelling of a place
    the writer may use (Kota Junction, Kota railway station); the same picture never closes one beat and opens
    the next (`desk/visuals.py`);
  - a beat that names a place and only quotes the police ("पुलिस के अनुसार, ... सूरत") shows the place; the police
    photo leads only a beat with no place or one naming that force ("मुंबई पुलिस"), and never a beat naming another
    force ("राजस्थान पुलिस": `visuals.other_force`); a place beat's second picture is another of its places or the
    story's route map, never the story's person (the first full-template dry run, 2026-10-21, put Mumbai Police
    under Surat and Kota and "रेलवे स्टेशन" over Tiger Shroff's portrait); in a story about a person, a beat that
    does not name them (the injured, the interrogation) shows the police for a beat about the accused, else the
    story's places, never their portrait (`visuals.assign(person=...)`);
  - a map shows the right spot (owner, 2026-10-20: "use the map correctly if you are showing mumbai there"): a
    place inside another the script names (Juhu in Mumbai) is marked on the city's map as "जुहू, मुंबई" and on a
    street map, a city named again shows that spot rather than its centre, and a route line joins only places that
    are apart (Kota and Mumbai), never a spot and its own city;
  - "there is no photo" is said only after searching Commons for it (the Tiger Short claimed one photo; Commons had
    nine);
  - real incident photos and footage belong to news agencies (Content ID, strikes, no monetization) and are never
    used; an AI-made picture of a real incident is never used either. The incident is shown by its place on a map,
    the people in it and the police and officials who speak;
  - before a change to the pictures is merged, a dry run is made and its frames are looked at, every beat.
- **What the voice says is what the screen shows (owner, 2026-10-21, furious: "If you are mentioning PM modi in
  the video where is the picture of modi ji"; "you are referencing in multiple videos same images").** The Modi
  Dussehra Short named him in its title and three beats and showed Delhi's temples, a market and a rickshaw; the
  Kota court Short held one Kota map under six of seven beats; one Film City photo went out in five Tiger Shroff
  Shorts. What changed, and what holds from now on:
  - a person the headlines name is the story's centre before the city they were in ("PM Modi attends Dussehra in
    Delhi" is about Modi; `explain.PERSON_LOOKS`); a city is the centre only when no person is named;
  - a place-centred story no longer drops every name the script lists (an empty subject matched every name:
    `visuals._subject`); a person is also named by their unique surname ("फडणवीस") and by the title the script
    puts before them in two beats ("प्रधानमंत्री": `visuals.surnames`, `visuals.titles`);
  - a person's photos are of them at the story's event first: a Commons search of their name with the word the
    headlines share ("Narendra Modi Dussehra" found PIB's photos of him at the Red Fort's Dussehra;
    `writer.story_words`); wax figures, statues, posters and cut-outs are not the person (`media.NOT_PERSON`);
  - Government of India photos (PIB, PMO) under the Government Open Data License - India are free to use with
    credit (`GODL-India`, licence link in the credit; never implying endorsement); agency and outlet photos stay
    forbidden;
  - a festival or tradition the script names (रामलीला) is pictured by its own Commons photos, never by a ground
    named after it (`visuals.TOPIC`, `topic_like`);
  - no picture stands under three beats in a row or more than half of a Short's beats (a place's maps count as
    one), a place shown in two beats gives way to anything else its beat names, a beat that names a person shows
    them, the title's person is on screen, and a place card ("उत्सव मैदान") sits only over that place's own map or
    photo (else it names the place on screen or goes); all gated in `gate.said_is_shown`, retried on failure;
  - each publish records the Commons files it showed; photos shown in the last 96 hours go last
    (`ledger.recent_photos`, `visuals.fresh_first`), and a Short is not made unless at least half (and at least
    two) of the photos on screen are new to those 96 hours (`writer.stale_pictures`; maps and tributes aside): the
    tenth Tiger Shroff Short in two days showed photos nine earlier ones had, and Commons has about nine of him;
  - when no town the script names has a police page, the police of the town a place lies in come next (Juhu lies
    in Mumbai: `visuals._cities_around`), and a beat right before a police beat leaves the police photo to it (the
    security Short put his portrait over "आरोपियों से पूछताछ");
  - a Short found wrong whose story is too old to remake is listed in `retire.json` and made private by the next
    run (TAuiM3yuZKk, jtpKgCtCNmw, 2026-10-21).
- **Editing from the channels that work (owner, 2026-10-20: "take reference of famous AI news channels ... add some
  positive skills while video editing").** A study of 47 Shorts on 16 channels (BBC Hindi, DW Hindi, Al Jazeera,
  AJ+, RealLifeLore and others; archived as `news-presentation-study-2026-10-20`) found what the strongest share;
  the full template has:
  - a hook card over the picture for the first 3.6 s (`scene.hook`, white box with a red offset shadow), a
    statement and never a question; a case angle gives its own;
  - a place stamp in the picture's top corner that follows the story's maps and landmarks (Juhu, then Surat,
    then Kota Junction), shown only over a map or a place's photo (over a portrait it put Tiger Shroff in
    Begusarai), and never gives "जुहू, मुंबई" away to the "मुंबई" it already names;
  - a one-second opening flash of the Short's other pictures (3-5 at a fifth of a second, with an accent), never on
    a loss story;
  - "हर अपडेट के लिए चैनल फ़ॉलो करें" on the end card.
  - name straps and the two-person split (2026-10-21).
  Next to build: a map built up layer by layer as the story moves (RealLifeLore), an attention ring on the detail
  the voice names.
- **Pictures:** at least three real, freely licensed photos and maps (photos from Wikimedia Commons: CC0, public domain, CC BY,
  CC BY-SA, GODL-India; never non-commercial or fair-use files), each credited by author and licence on screen (`फ़ोटो: author /
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
  the official statement; क्यों (or that no official reason was given); आगे क्या. The other side appears only in a
  dispute between two named sides and only when it replied; never for a crime or an attack, and never a line that
  someone "has not responded" (`writer.NOBODY_REPLIED`) or a career summary (`writer.BIOGRAPHY`, except a death).
  Third person, no
  viewer address (आइए, दोस्तों, जानिए), no exclamation, no rhetorical question, no question title, no biography
  padding, no moral or conclusion; `writer.casual` rejects a draft that slips. A death is a news obituary report.
  Cards carry the key fact (a number with its unit whenever the beat has one) and a label, never a place alone.
- **Everyday Hindi, searchable titles and hashtags (owner, 2026-10-19: titles and captions in "very hard hindi",
  "hashtags are not working").** Evidence: plain name-first titles (Nana Patekar 1,301, Rahul Gandhi 593, Imran Khan
  321) beat titles that open with an office or a full institution name ("जस्टिस जेबी पारदीवाला की पीठ...",
  "अन्तर्राष्ट्रीय मुद्रा कोष...", 6-50 views); Wikidata's formal Hindi labels (IMF, IMD, Supreme Court) were being forced
  into scripts; every description led with "...की रिपोर्टों और Wikipedia से" and ended with three joined-up Devanagari
  hashtags and no `#shorts`. Aaj Tak, ABP News and NDTV India title Shorts "<name or topic in English>: <Hinglish
  headline>" and tag the subject in English letters plus `#shorts #hindinews #latestnews`. Now: the narration (which
  is also the subtitles) is the spoken Hindi of Aaj Tak/ABP; `writer.bookish` sends back `HARD_WORDS` in narration or
  cards, "स्रोत के अनुसार", and more than two "रिपोर्टों के मुताबिक" (not on the last draft, so a story is never lost to
  wording); formal Wikidata labels never bind (`writer.everyday_names`); `writer.hashtags_for` gives the subject tag, its `news` form, `#hindinews
  #shorts`, a topic tag and the broad tags (at most 14); the description opens with the title and the hashtags; the
  YouTube title carries `#shorts` and the subject tag when it fits 100 characters (`youtube.upload_title`), while the
  ledger and the on-screen headline keep the plain title.
- **Natural headlines, the name first (2026-10-22).** The "Name: headline" template is retired: those 20 Shorts drew a
  median 35.5 views against 55 for the other 54, and the five ending "वजह क्या है" 17; one template on every title
  also reads as mass-produced. A title is one natural Hindi headline with the name or topic people search for in its
  first three words, making one concrete claim or asking the one specific question the Short answers. The headline
  brief sees the channel's last 20 titles. `writer.title_style` flags a "Name:" label (`writer.KICKER`), a stock
  tail ("वजह क्या है?", "क्या थी वजह?", a bare ", क्यों?"), a name later than the first three words, and the same
  first three words as any of the last 20 titles of other stories; it is advisory in the headline editor's last
  round, so a story never loses its title to it. Every hard title check (`writer.title_problems`) is unchanged.
- **The name people know (owner, 2026-10-21: "you are saying jakie shrof to jay kissan shrof ... what all people
  know that word will reach to maximum peoples").** Wikidata's first Hindi label is sometimes a birth name (जय किशन
  श्रॉफ for Jackie Shroff). `wiki.common_hindi` keeps the label when it sounds like the English
  name, otherwise picks, from the label, the Hindi Wikipedia title and the Hindi aliases, the one closest to the
  English name (a full name over a lone surname), with `wiki.NEWSROOM_HI` for spellings newsrooms fix (डोनाल्ड
  ट्रंप). It names the script, the strap, the police photo and the title; a spelling two owners' reports print is
  also accepted. `HARD_WORDS` sends back bookish words for the ones TV says (फायरिंग, आरोपी, FIR, अस्पताल, इलाज,
  गाड़ी, बयान, जांच, SP, पुलिस कमिश्नर...).
- **A spelling must not read as another name (2026-10-22).** The Chennai rain Short wrote Parrys as पैरिस, which
  every Hindi reader takes for Paris. `writer.misread` looks each name with no Wikidata label and no Hindi source
  spelling up in `wiki.hindi_readings` (Wikidata items whose Devanagari label writes that word, whole or as its first
  word; cached for the run) and sends the draft back when the spelling sounds more like another item's English
  name than the story's (advisory, never on the last draft). The writer's rules say so up front. Known limit: the
  Aubagne Short's ओबान is not caught, as Wikidata has no Hindi label for Aubagne and no item is spelled ओबान (only
  ओबानज़वा); once a label exists the writer is held to it like any other.
- **Engaging and visibly sourced (owner, 2026-10-13: "more attractive news ... 100% engaging ... real facts").**
  Every frame carries the channel strip (`मतलबनामा · राजनीति`, the story's kind or explainer category) and a thin
  progress bar along the top edge; the opening shot names where the facts come from (`स्रोत: बीबीसी · द हिंदू ·
  Wikipedia`). The script's first five words carry the news (never a date, a question or a slow introduction),
  every beat adds one new sourced fact, and the last beat is a short factual sentence. Engagement never comes from
  hype: the banned-wording list and every fact check still apply.
- **काम की बात: every Short adds value (2026-10-22, for YouTube's Partner Programme).** The last beat of an incident,
  protest or explainer says what happens next (a hearing, a deadline, the next official step) or what the news
  means for people (a closed road or service, a changed rule or price, compensation), only as the sources state it
  and attributed. `writer.value_beat` checks the last beat for such words (advisory, never on an obituary or the
  last draft). No advice: `writer.advice` sends back a beat that tells viewers to buy, invest, take medicine or
  "आपको ... चाहिए", or that gives an unnamed expert's advice (विशेषज्ञों की सलाह), above all on money, health or law.
  Reporting is not advice: "विशेषज्ञों की सलाह पर स्कूल बंद किए" (why something was done) and a quoted, attributed
  appeal pass, unless the quote's speaker is an unnamed expert. Like the other style rules it is advisory on the
  last draft, so a false match never costs a story; the writer's prompt and the fact checker still forbid advice.
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
- Corrections: a viewer reports a mistake in a comment or by email (the About gives both); a confirmed wrong fact
  means the Short is made private and, while the story is still news, re-made (`remakes/`). The desk posts no pinned
  comment, so neither the About nor a description promises one.
- Titles and descriptions (2026-10-22): the title's hashtag is someone the title names (`youtube.title_tag`; the
  explainer's subject tag stays only when the title names the subject), digits are Latin and famous names have one
  spelling (`hindi.SPELLINGS`, `hindi.respell`); every non-advisory description carries one "कैसे बनी:" line
  (`youtube.HOW_MADE`) within the 5,000-byte limit.
- Remakes: a published Short that is wrong or badly presented is re-made by a file in `remakes/` (`story`: the
  published id, `replaces`: its YouTube id, `until`, `why`). While its story is still on the radar the next run in the
  publishing window makes it again under a new id, ahead of the other ready stories, and once the new version is
  public the old video is made private (the ledger row records `replaces` and `replaced`). The Tiger Shroff Short
  (zl1DewTqnP8) was the first, 2026-10-20.

## Operations

- The half-hourly GitHub Actions run (`run.yml`) is the only automatic publisher. Its state lives on the `state`
  branch. The repository variable `PAUSED=true` holds the schedule and the health alerts; manual dry runs still work,
  and a manual run that would publish refuses while paused.
- Secrets live only in the GitHub environment `youtube`: `GEMINI_API_KEY` and `YOUTUBE_OAUTH_JSON`. The key travels
  only in a request header and is never logged or written to disk.
- An open issue labelled `alert` means the desk needs attention (a failed run, four hours of silence, or a hold such
  as no Sulafat voice); GitHub emails the repo owner.
- **No machine tag on uploads (2026-10-22).** Tags are the story's topic tags and the channel's name only; the old
  public `hindi-news-desk:<story id>` tag is gone. The desk knows its own uploads by video id: `state/uploads.json`
  keeps each story's video id the moment YouTube returns it (the state branch is saved even when a run fails), and
  `youtube.find` takes that id, then an older upload's marker tag (`config.MARKER`, kept for the uploads before
  this date), then the one recent upload no ledger row owns whose title is the story's. The repository variable
  `DESK_UNTAG=true` (off by default; an owner action) lets each live run take the old tag off five of the recent 50
  uploads after keeping their ids; uploads older than the newest 50 keep it. Editing a video (`videos.update`) needs
  the `youtube` or `youtube.force-ssl` scope: a token that lists neither is never sent, and a 403 stops the step;
  either way one health line (`youtube.UNTAG_NO_SCOPE`) says the token needs re-consent, and nothing else changes.
- **Channel setup (`desk/channel.py`, 2026-10-22).** The same variable takes more words: `DESK_UNTAG="untag about
  playlists"` (`true` still means untag only; `run.yml` passes no other variable and is not edited; each word is
  separate, so `DESK_UNTAG="about playlists"` sets up the channel and leaves untag off). `about` writes
  the About (`channel.ABOUT`, at most 1,000 characters), keywords, `defaultLanguage` hi and country IN by
  read-modify-write of `brandingSettings` (its title is required), then reads it back (whitespace aside); a version
  YouTube refuses (HTTP 400) or does not read back is recorded in `about_failed` and not written again until
  `channel.ABOUT` changes. `playlists` makes one public
  series playlist per ad-friendly topic family (`channel.FAMILIES`) once it has two public, unreplaced, unretired,
  ad-friendly Shorts, adds them from the ledger's video ids, and gives each a Home-tab section (a 400/404 refusal is
  noted and not retried; a 5xx or timeout is retried next run; a playlist that refuses position 0 gets new Shorts at
  its end). Review the first playlists by hand: the ledger's categories are not always right. `state/channel.json` keeps what is done, so a finished job costs nothing; each run spends at most
  600 units and each Pacific day 1,500 of the 10,000, and only after the publish step of a run that is not held. A
  `quotaExceeded`/`dailyLimitExceeded` or other 403 stops it until the next Pacific day, a rate limit only for the
  run; one health line says what happened, and no error of it can stop a publish.
- Never promise views or earnings; growth comes from accuracy, consistency and clarity.

## Decisions log

| Date | Decision | Evidence |
|---|---|---|
| 2026-10-22 | YPP push, batch 2: no public machine tag; ad-safe ranking (x0.8 crime/court/communal/accident, x1.2 economy/jobs/schemes/tech/science/diplomacy, breaking exempt); Orbitwire's stories retold only with an India connection; misread-spelling check; natural name-first titles (no "Name:" label, no "वजह क्या है" tail, no repeated opening); काम की बात last beat and no advice; retention from YouTube Analytics. Style rules are advisory on the last attempt; no fact, licence or decorum gate loosened. | Views per Short on the state branch, 2026-10-21: "Name:" titles median 35.5 (n=20) vs 55 (n=54); "वजह क्या" titles median 17 (n=5: 321, 160, 17, 16, 4); category medians attack 85 (n=13), court 112.5 (6), economy 29 (5), news 44 (18), death 732; region medians world 48 (n=29), india 53 (n=41); only one Short ever recorded an Orbitwire overlap (Nana Patekar). Wikidata, 2026-10-22: पैरिस is the Bhojpuri label of Paris (Q90) and the first word of University of Paris and Treaty of Paris; Aubagne (Q184047) and Parry's Corner (Q3406502) have no Hindi label; ओबान only begins ओबानज़वा. No view or earnings promise is made: the ad reweight trades some views for suitability. |
| 2026-10-22 | Batch-2 review fixes: the advice check is narrowed (no "की सलाह पर", no quoted attributed appeal) and advisory on the last draft; with `MIRROR_NEEDS_INDIA` off a world story without an India connection keeps its own angle; Hindi ad keywords that are part of another word and catch-all English words (talks, visits, prices, projects) no longer count, and a market crash is no accident; the retention window opens a day early (Pacific days) and ends three days back; untag checks for a write scope and reports a missing one in one line. | Review of the batch-2 branch, 2026-10-22, by running the checks: "सरकार ने विशेषज्ञों की सलाह पर स्कूल बंद किए" and `मोदी ने कहा, "आप सब मतदान करें।"` were rejected on every draft; `मैच के दौरान खिलाड़ी घायल`, दामाद, नियमित, "Kohli talks about retirement" were ad-friendly; "Stock market crash" was ad-sensitive; with the switch off every shared world story got the India angle and a भारत title rule. YouTube Data API: `videos.update` needs `youtube` or `youtube.force-ssl`; YouTube Analytics reports days in US Pacific time. |
| 2026-10-22 | YPP push, batch 3: the About says what the desk does (economy, prices, jobs, schemes, science; named newsrooms plus Wikipedia/Wikidata; two outlets; AI voice and AI-assisted script; human-made editorial rules; corrections by comment or email, no pinned comment) and drops हादसे/युद्ध; series playlists by ad-friendly topic family with Home sections; the title hashtag is whom the title names; Latin digits and one spelling per famous name; a "कैसे बनी" line in descriptions. All channel writes are owner-gated (`DESK_UNTAG` words), capped and idempotent. | JEm0Ivq1_74 (Ashutosh Ranka story) carried #sauravdas because `upload_title` always took `hashtags[0]`, the explainer centre's tag, while the writer's title led with Ranka; its ledger article "Sourav Das (actor)" also looks like a wrong entity match (not fixed here). The old About promised a pinned correction the desk never posts. YouTube Data API: `channels.update` replaces the whole `brandingSettings` part and needs its title; writes cost 50 units; the About allows 1,000 characters and keywords 500. No view or earnings promise is made. |
| 2026-10-22 | Channel renamed Kyun Hua → मतलबनामा \| Matlabnama, handle @KyunHuaHindi → @Matlabnama (same channel id); About, keywords, playlist suffix and tags follow; repo variables `DESK_CHANNEL_NAME`, `DESK_CHANNEL_NAME_HI`, `DESK_CHANNEL_HANDLE` set | "Kyun Hua" names one beat of the format (why it happened) while every Short also says what happened and what it means for the viewer; it read as an unfinished phrase in search and on the end card. "मतलबनामा" ("the meaning, in writing") names the promise, is one searchable word, and had no existing YouTube channel. Decision note: `audit/kyun-hua-name-decision.md` |
| 2026-10-22 | Gating metrics (strategy P0-1): the retention query also reads plays, seconds watched, subscribers gained, likes and shares per Short; a metric the report refuses (HTTP 400) is dropped alone and listed, never views or average percentage viewed; traffic sources (`insightTrafficSourceType`) for at most 30 Shorts a run, three to 28 days old, each at most daily. Read-only; nothing in the ranking uses them yet. | No per-video subscriber or traffic data existed: the 14-day rules (engaged share, subscribers per 1K engaged views, traffic mix) could not be computed from the state branch. Channel Doctor issue #2 (data to 2026-10-20): 20 subscribers, 1.88 per 1K engaged views, only 3 videos ever gained one. The old 400 fallback could only drop `engagedViews`, so one refused new metric would have lost retention for every Short. `audit/kyun-hua-shorts-strategy.md` §1, §6, §10. |
