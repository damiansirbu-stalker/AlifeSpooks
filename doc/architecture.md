# AlifeSpooks - architecture and method

AlifeSpooks is a dark ambient layer for S.T.A.L.K.E.R. Anomaly and G.A.M.M.A. It gathers the
dreadful, mournful, and eerie sounds from community soundscape packs, measures and deduplicates
them, and plays them as positioned one-shots driven by a runtime director that reads where the
player stands and who is near. It does not add engine ambient channels and it does not edit an
ambient file. It plays its own sounds, and it mutes the base game's copy of any sound it also ships.

This document is the method and the invariants. The build tool is `tools/merge.py`. Every number
below is reproduced by a subcommand of it, not chosen by hand.

## Model: a one-shot director, no channels

The old model shipped our sounds as engine sound channels (`sound_channels.ltx` sections) and let
the ambient system play them. That is gone. AlifeSpooks now owns playback end to end:

- Content lives in our own category directories under `gamedata/sounds/zs/<category>/`, never in an
  engine channel. The deploy writes no `sound_channels.ltx` definitions for our content.
- The director (`gamedata/scripts/as_director.script`) plays each sound as a positioned one-shot
  through `xsound.play`. There are no loops and no continuous beds. A long horror drone or a psy bed
  plays as a one-shot on a long period, not as a continuous loop.
- The base's own copy of a sound we ship is removed from its ambient channels statically by a DLTX
  overlay at config load (the veto, below), so the base never doubles the director. A separate observer
  owns the vanilla `update_ambient` slot only to replay and log the base ambient.

Because the director is the only playback path, xlibs (`xsound`) is required. Without it the mod is
inert: no sound plays.

The category is the unit of organization and of play. It is a directory of sounds plus two attributes -
an `env` set (which enclosure states it may play in) and a `requires` gate (a live precondition) - with
no weight and no cooldown. The director reads a generated manifest (`as_manifest.script`) that lists each
category, its sounds, and each sound's distance and height. The manifest replaces the channel
definitions the director used to read from `sound_channels.ltx`. Anomaly Lua cannot enumerate a
directory at runtime, so the deploy writes the manifest and the director reads it. See "Categories - the
rule table" below; the category list is the single source of truth.

## Content pipeline (reproducible)

`tools/merge.py` is a six-stage pipeline. Each stage is a subcommand that reads the previous stage's
committed artifact and writes the next. Adopting a pack is additive (`add`) or a full re-run, never a rewrite.

```
plan        source trees, deduped by waveform        -> merged_channels.json
classify    measured features per sound              -> classification.json
loudness    per-group loudness, outliers flagged     -> loudness_outliers.json
deploy      audio + manifest + veto DLTX overlay     -> gamedata/
ledger      content-hash proof of coverage           -> ledger.tsv
provenance  every shipped sound -> its origin         -> provenance.tsv
```

- plan (`cmd_plan`): walk every source pack's sound tree and route each FILE to a category by its
  folder path (`route` / `ROUTE`), a structural per-file allowlist - the packs ship far more dark
  content than they wire into a channel, so the folder trees are the source of truth, not any config
  list. Gate on sample rate, drop dead-silent files, deduplicate by waveform, then the long-file pass:
  a sound whose ACTIVE (silence-removed) length exceeds the max emission tick is culled, except
  `dark_signal`, which is sliced into short desilenced pieces (`_long_file_pass`). Output
  `merged_channels.json` (the curated corpus) and `folder_audit.tsv` (which folders each category pulled).
- classify (`cmd_classify`): one ffmpeg pass per sound for duration, spectral centroid and flatness,
  and crest. There is no loop-versus-effect decision. Everything is a one-shot.
- loudness (`cmd_loudness`): measure integrated loudness per sound and flag per-group outliers.
- deploy (`cmd_deploy`): measure each source's peak and average loudness and CULL the near-silent
  (`_loudness_cull`), copy the survivors byte for byte to `zs/<category>/<n>.ogg`, write each file's blob
  with source attenuation plus a base_volume that levels the sound to the corpus-median loudness
  (`_normalize_blobs`), write the sound manifest the director
  reads (`as_manifest.script`), and generate the base-veto DLTX overlay that removes our sounds from the
  base ambient channels (`_veto_dltx` -> `mod_sound_channels_alifespooks.ltx`).
- ledger (`cmd_ledger`) and provenance (`cmd_provenance`): the proofs, below.

### Selection is manual, pulling is mechanical

Which packs and which folders contribute is a per-pack judgment, made by hand before any pull. Each
new pack is opened and assessed for what dark content it actually holds, and its folders are mapped
to categories by adding rows to `ROUTE` (the structural per-file table `route` walks). The folder-path
match is only the mechanical pull that runs after that decision; anything unmatched is dropped (dark
scope). There is no keyword classifier that decides scope on its own. The `UNUSED-DARK = 0` ledger
invariant then confirms the hand-written rules captured every dark file the pack holds.

The source list is the registry `tools/sources.py` (n124): one declarative entry per pack - `name`, local
`path`, reference `url`, `licence` - and `MODS` derives from it (`sources.mods()`), preserving the exact
order (dedup is order-sensitive). Sources are ALWAYS pulled locally by hand; the pipeline never downloads,
so the `url` is a credit/provenance reference only (readme, licensing), nothing fetches it. A licence gate
(`check_licences`) stops the build on any source not cleared (`licence = pending`). `merge.py provision`
reports each source present or MISSING using the build's OWN capture (`<path>/sounds/*.ogg`), so a wrong
path shows up here instead of being silently skipped - and `_scan_source` now WARNS loudly rather than
quietly `continue`ing past a source with no `sounds/` (the defect that hid AmplifiedVanilla from every build).

### Identity and build modes (identity DONE; additive `add` implemented; registry n124-planned)

`cmd_deploy` names each file by content, not position - `_deployed_stem` = `<origname>_<audiohash>`.
The old positional `zs/<category>/<N>.ogg` (`N` = enumerate order) was a collision workaround (many
packs ship the same filename), but it RE-INDEXED every file whenever content was added or removed, so a
build could only run from scratch. The content name fixes that. IMPLEMENTED today:

- Name = original name + audio hash: `zs/<category>/<origname>_<hash>.ogg`, `hash` = `_audio_hash`
  (md5 of the audio pages only, blob-agnostic) in short form. Readable (keeps the source name), unique
  (the hash disambiguates two files that share a name), stable (identical audio always maps to the same
  name; adding content never renames an existing file).
- Origin (mod, folder, original path) stays in `provenance.tsv` keyed by the name, never baked into the
  filename - the path is long and shifts if a source reorganizes, while the audio does not.
- Exact-dedup key: the full build's stage-1 keys on `file_hash` (whole-file md5), and audio-identical
  copies that differ only in their blob collapse at the fp/xcorr stage; `add` matches a new sound against
  the published set by the `_audio_hash` tail carried in each deployed name. Tightening the full build's
  stage-1 to `_audio_hash` (so name-uniqueness holds before the fuzzy stage too) is a pending robustness
  step (n124).
- Re-encode / near-clone detection = Chromaprint fp + PCM xcorr, COMPUTED ON DEMAND from the `.ogg`
  files during a build, never persisted. A fingerprint is derived data, not identity; only the exact
  hash rides in the name, because the name itself needs a unique stable id with no side registry - that
  is naming, not a cache. There is no fingerprint cache.
- Two build modes:
  - full (`all`): whole source pool -> route -> dedup -> name -> write, then ledger + provenance. The
    canonical corpus.
  - additive (`add <source> <gamedata>`, IMPLEMENTED): the published corpus is FROZEN, keyed on the CORPUS
    OF RECORD (the audio hashes of the existing `merged_channels.json` entries, not the post-cull deployed
    files - keying on the deployed files re-proposed culled sounds every run and never converged). Route the
    new source with the shared capture rule (`_scan_source`), waveform-dedup it against itself, drop anything
    already in the record (audio hash) AND any re-encode of a published sound (fp + PCM xcorr,
    `_drop_frozen_reencodes`), APPEND only net-new (new names, existing untouched), then regenerate classify +
    deploy. It SKIPS the slow full plan and the ledger, so an add runs in minutes, not the full ~25. A re-add
    of an already-ingested pack is idempotent (`+0 net-new`). Limit: deploy re-emits the whole corpus from
    source (the packs must be on disk); a full `all` reconciles `merged_channels.json` (gitignored, so a
    build rebuilds it from scratch) and refreshes the ledger + provenance proofs.
- Honest limits: re-encode detection is heuristic (fp >= 0.88 candidate, xcorr >= 0.90 decide), not
  exact; additive freezes existing choices, so it can diverge from a fresh full build at the margins -
  `build` is canonical, and a full rebuild reconciles.

## Deduplication: waveform identity, source side only

Identity is decided by the waveform, never the filename or the bytes. Three stages, cheapest first,
so the expensive test runs only on the pairs the cheap ones flag (`dedup_pick`, `pcm_correlation`).

- md5: byte-identical reships across packs collapse to one.
- Chromaprint fingerprint (`fpcalc`, >= 0.88): stable across bitrate and codec, so it finds the
  re-encoded copies md5 misses. Its same-versus-distinct ranges overlap, so it only proposes
  candidate pairs and never decides.
- PCM cross-correlation (`DEDUP_XCORR` = 0.90): decode both, align by envelope, correlate over the
  overlap. A re-encode scores near 1.0, a distinct sound near 0. Two files merge only under
  complete linkage, so a similarity chain never collapses two distinct recordings and variety is
  never lost.

This runs among the source packs only, within a pack and between the packs we pull from. AlifeSpooks
does not deduplicate against the target modpack. It never drops a sound because the install already
plays it. Doubling with the base is handled by the static DLTX veto overlay at config load.

## Byte-for-byte audio, loudness-leveled blob

Every kept sound's AUDIO ships byte for byte - no re-encode, the vorbis pages are untouched. What the
deploy writes is only the X-Ray ogg comment blob (min distance, max distance, base_volume), a lossless
header-page rewrite (`_write_blob`); the audio pages stay byte-identical.

- **Attenuation** (min/max distance) is the source's. A file that carried a source blob keeps its
  min/max; a blob-less file gets the median min/max of its category-folder peers.
- **Loudness is leveled via base_volume** (`_normalize_blobs`, `_level_bv`). base_volume is a linear
  multiplier the engine applies on every play (see `sound-source-and-emitter.md`). Every file's
  base_volume is set so its AVERAGE loudness (astats Overall RMS) lands on the CORPUS MEDIAN - one global
  target for every sound, so loud sources come down and quiet ones come up to the same felt level, without
  touching the samples. The gain is peak-capped at -1 dB so nothing clips: a file too spiky to reach the
  median without clipping is left peak-normalized and counted as capped. base_volume is floored at `BV_MIN`
  so a down-leveled sound is never pushed under the engine cull. Equal peaks do not sound equally loud (the
  earlier peak-match, n107/n108, left dense sources blaring and spiky ones deaf); equal RMS does. n014's
  ffmpeg re-encode was destroying the blob; the blob-number edit does not.
- **Loudness cull** (`_loudness_cull`, `CULL_PEAK_DB`): a file whose measured peak is below -30 dB
  cannot reach target without absurd gain (that is amplified noise, not a quiet sound), so it is DROPPED,
  not shipped. The older `_silence_gate` (drops only true -inf) still runs first. No near-silent file
  survives - a distant/faint feel comes from the director's POSITIONING, never from a quiet source file.

The manifest carries each sound's min distance, max distance, and height, inherited from its source
channel settings, so the director can position the sound before the engine applies the blob.

Fitness gate: 44100 Hz vorbis only, the X-Ray standard. Off-rate and junk-bitrate files are dropped
and accounted, never silently.

## The director

The director owns playback on ONE 100ms tick (`("as_director","tick")`, separate from the base-ambient
observer). Each tick round-robins ONE producer that writes its sensor into a flat board, derives dread
and the eligible set from the board, and emits at most one positioned one-shot. The per-tick cost is the
single heaviest scan, never the sum; the whole board refreshes over the producer count (~0.6s).

    tick   -> run one producer (a scan), writing its sensor into the board
    sense  -> the board: environment, time, stalkers{}, monsters{}, anomalies{}
    select -> eligible = map (as_static_map.ltx) & environment & presence -> two-level shuffle-bag
    apply  -> dread (grounded, additive) -> spawn distance + emission frequency -> position + play

Smart terrains are deliberately NOT an input - they proved unreliable for filtering (the trader/base
cases); place identity comes from the level, the environment, and a live seller check, never smart config.

### The board - the world as tokens

The board is the single source of truth: producers write it, SELECT / APPLY / the HUD read it. Values are
readable tokens, never raw ints or paired flags. Two sensor classes - SCAN (polled on the round-robin) and,
later (n118), EVENT (bumped by callbacks, decayed). A sensor's fields match what is useful: mobile things
carry `online` + `near`, static anomalies carry only `near`.

- `environment` - "outdoor" | "indoor" | "underground" | "labs". `GetEvent("underground")` says you are on
  an underground level; `LAB_LEVELS` splits the sci-fi labs from the tunnel/mine/bunker levels; else the
  `is_indoor` raycast (cached by cell) gives indoor vs outdoor.
- `time` - "day" | "dusk" | "dawn" | "night" | "deep_night".
- `stalkers` - one pass over the dedicated `db.OnlineStalkers` array (`_scan_stalkers`): `online` (any
  stalker online, the gunfire gate), `enemy_near` / `ally_near` (strongest near hostile / non-hostile as a
  low/med/high power - neutral counts as company, only per-NPC enemy relation is a threat), `service_near`
  ("none"|"allied"|"hostile" - a trader/medic/mechanic within 60m = a base).
- `monsters` - one pass over `xcreature.online_monster_iter` (`_scan_monsters`): a demonized `db.OnlineMonsters`
  id-array when present, else a best-effort `is_mutant` walk capped at `MONSTER_ITER_CAP` online objects so the
  scan stays bounded under soak (a monster past the cap is missed); the registry PR is the parity fix (n119):
  `online` (the mutant gate), `enemy_near` (strongest near monster as a power).
- `anomalies` - `near` (an anomaly within range, `xsmart.anomaly_near`), the drone gate.

### Power - man and monster on one scale

Every hostile near thing is graded "none"|"low"|"med"|"high" by `_tier(rank)`: a stalker's `character_rank()`
(0-27000, cuts 9000/14500) and a monster's `se:rank()` (1-20, cuts 5/16) collapse to the SAME token. So
`stalkers.enemy_near` and `monsters.enemy_near` are the same type, and threat reads both with one rule
(`max`). The engine facts and the probe-verified monster rank table are in
`doc/library/modding/npc-strength-evaluation.md`.

### The tick and the emission gate

The tick runs a fixed 100ms and never stops, so a rising dread is always caught; the board refreshes over
the producer rotation. Emission is separate: a sound fires at most every 5-15s and dread shortens that gap
(scarier -> denser). Below ~0.10 dread nothing emits (calm places quiet, a friendly base silent), while the
tick keeps sensing. No per-category cooldowns, no weights.

### SELECT - which categories can play

A category is eligible only if all three checks pass, in order (`_eligible`, reading the board):

- **map** - the level's list in `as_static_map.ltx` names it. `[default]` holds the universal cues on
  every level; each `[level]` adds its terrain flavor, its interior/facility kinds, and the `dark_signal`
  lore placement. A lab level lists `labs`, a swamp lists `mutant_ambient_swamp`, a wild forest never
  lists `dark_signal`.
- **environment** - the category's `env` set contains the current `board.environment` (labs counts as
  underground for the gate). Outdoor never plays the inside kinds (structural, labs, drip, rats); indoor
  never plays the outside kinds (foliage, wind, wildlife, urban, the zones).
- **need** - a live gate: `mutant` needs `monsters.online`, `gunfire` needs `stalkers.online`, `drone`
  needs `anomalies.near`; the rest, none.

The base is NOT a select filter: a friendly base is silenced by APPLY (dread -> 0), not by category gating.
Selection is a **symmetrical two-level shuffle-bag**, no weights: a category-bag cycles every eligible
category once before repeats (a 2-sound category can never be hammered while others wait), and a per-category
sound-bag cycles every sound once. Rarity emerges from rotation, not from any limiter.

### APPLY - dread drives distance and frequency

Dread is a scalar 0..1, additive, **no baseline constant** - the sum of whatever grounded conditions hold now:

    dread = lore + environment + time + threat + company + anomaly

- **lore** - the level's own baseline (grim in the psi north and the labs, mundane in the fields).
  Coordinate overrides supersede this later (n114).
- **environment** - outdoor +0; indoor +small; underground +med; labs +big.
- **time** - day +0; dusk/dawn +small; night +med; deep night +big.
- **threat** - the single scariest near thing, `max(stalkers.enemy_near, monsters.enemy_near)`, scaled by
  its low/med/high power (man and monster the same); if no living thing is near at all, loneliness +small.
- **company** - a near non-hostile stalker calms (neutral or friendly - any human presence breaks the
  isolation), scaled by its power (a veteran calms more).
- **anomaly** - an anomaly near adds a little.

A `service_near` of "allied" (a safe hub) REPLACES the sum with 0 - fully silent; "hostile" (an enemy-held
base) adds. The base is detected by a live service NPC (trader/medic/mechanic) within 60m, per-NPC relation
deciding allied vs hostile - warfare-correct, never the over-assigned `is_base` prop. Every term is grounded,
so there is no "+X just because." Dread feeds APPLY only, never SELECT: **distance** (closer at peak,
`HORROR_PULL`), **height** (an overhead cue descends toward you at peak, same `HORROR_PULL`), and **frequency**
(shorter gap). It never touches **volume** - volume is the sound's own leveled level x one master MCM slider.
Positioning uses Anomaly's own geometry: `emit` places the sound at a HORIZONTAL `dist` (a random point in the
source min..max band, halved, pulled closer by dread) in a random direction, and VERTICALLY at `pos.y + height` -
the sound's ORIGINAL source-channel elevation, recovered per sound by merge.py `_source_height_map` (aggregated
across packs, highest non-zero wins) and carried in the manifest as `snd[4]`, so an overhead sound (bird, vent,
thunder) stays overhead when calm - and, by the same dread pull as distance, descends toward ear level as the
place turns. The engine's baked attenuation then does the fade.

### Emission model - how the final loudness is set (engine-grounded)

The engine computes the audible gain per play (`SoundRender_Emitter_FSM.cpp:383`):

    gain = base_volume x volume_att x effect_volume x occlusion x fade

- **base_volume** - the per-file value in the ogg comment blob (X-Ray native, `SoundRender_Source_loader.cpp:129-136`).
  A direct linear multiplier, applied to mono AND stereo alike. The deploy OVERWRITES it for every file
  (`_normalize_blobs`), leveling each sound's average loudness (RMS) to the corpus median, peak-capped at
  -1 dB - so the whole corpus sits at one felt level, loud sources brought down. The source's authored
  base_volume is measured but not carried into the deployed blob; only the source min/max survive.
- **volume_att** - LINEAR distance attenuation `(max_dist - dist)/(max_dist - min_dist)` (`:361-362`): full at
  `min_distance`, silent at `max_distance`, NOT inverse-square. min/max sit in the same blob (the engine reads
  them) and in the manifest (the director reads them to position).
- **stereo** - OpenAL does not positionally spatialise a stereo buffer (`TargetA:212`), so a stereo sound loses
  DIRECTION (panning); the engine gain still applies, so it likely still fades with distance (runtime-confirm).
  Downmix is a directionality fix, not a loudness fix.

So the two per-file levers we control are `base_volume` (loudness) and `min/max` (attenuation range), both in the
blob; `height` (elevation) and the placement are the director's, in the manifest and `emit`.

### Visual layer

Only when dread is at its peak (>= 0.80) a short distortion pulse fires occasionally through xlibs
`xpp`, dwell-gated so a momentary spike never flashes, on a cooldown. This is the one place a threshold
on the continuous dread still matters; there is no grade ladder otherwise.

### Debug HUD (`as_hud`, off by default)

A three-column readout (MCM `hud_position`), built lazily on read so it costs nothing on the tick, grouped
by stage: PLAYING (the director's current one-shot + the base ambient the observer replays, each bright
while sounding, gray once stopped), SELECT (the available category list + the DREAD number, tinted gray /
amber / red by value, no rainbow), and SENSORS (every board field by its exact name - `stalkers.enemy_near`,
`monsters.online`, worded tokens, never a raw int). Players never see it; it feeds off
`as_director.get_hud_rows`.

## Categories - the rule table

A category is atomic: one coherent thing (one dread kind, one zone), never a grab-bag. The category is
the unit of organization - it is the shipped folder (`zs/<name>/`) and the manifest key. **The pipeline
category list carries only the name and the folder routing** (`CATEGORIES` + `route` in `merge.py`); it
holds no play rules. A category's runtime attributes - its `env` set, its `requires` gate, the per-map
eligibility, the presence checks - live in the director (`as_director`) and the per-map LTX, keyed by the
category name. The manifest carries sound paths and distances only; the category NAME is the entire
contract between the pipeline and the runtime.

The 20 categories:

- creature - `mutant`: one pooled bag, gated at runtime on any real mutant being present (a single
  boolean, not per-species). Fed by `monsters/<species>` (combat filtered out), `soundscape/mutants`,
  and the flat `spooks_above/mutants` trees. Species is preserved in provenance only, never a subfolder.
- zone ambience - `mutant_ambient_forest` / `_swamp` / `_urban` / `_field`: per-zone horror-mutant
  atmosphere, map-selected per level, no time and no species. Fed by the terrain-split
  `trx/spooks_above/<zone>{day,night}mutants` trees.
- ambience - `spook`, `scream`, `drone`, `dark_signal`, `industrial`, `structural`, `labs`, `drip`,
  `wind`, `foliage`, `wildlife`, `urban`, `gunfire`, `rats`, `bats`.

Categories are de-mixed from the source structure by folder path (`spooks_above` = surface,
`spooks_below` = underground): the old `machine` bucket becomes surface `industrial`; the underground
mega-bucket becomes `labs` (`underground` is now only the enclosure STATE, never a category); terrain
mutants split off into the four `mutant_ambient_<zone>` zones; `creak` becomes `foliage`; vermin split
into `rats` and `bats`. A category is split only along a filter axis the runtime acts on (env, per-map
zone, presence) - that is why the four zones are separate categories but the underground kinds collapse
into `labs`.

## The base-veto: static DLTX removal, plus a logging observer

The base game's System B (Lua `sound_ambient.update_ambient`) plays the rotating dread/atmosphere
one-shots - the vanilla "fake" spooks, drones, and distant-mutant growls. If the player also runs a
soundscape pack the mod drew from, the base plays the same sounds the director does, so they double.
AlifeSpooks removes its own sounds from the base's ambient channels STATICALLY, at config load, and
runs no muting loop at runtime.

### Static removal (the muting)

`tools/merge.py deploy` generates a DLTX overlay, `configs/environment/mod_sound_channels_alifespooks.ltx`
(`_veto_dltx`). For every base ambient channel that lists a sound whose AUDIO is one of ours, it emits
`![channel]` + `<sounds = <path>` - a per-item DLTX removal (`Xr_ini.cpp:238-240`) that strips exactly
that sound from the channel's `sounds` list and leaves the channel's other sounds. The composed
`sound_channels.ltx` the game loads no longer lists our sounds, so vanilla's own `update_ambient` (and
the engine bed) never plays them. It is deterministic, engine-native, and survives anything at runtime -
there is no slot to lose.

- Identity is the audio-page hash (`_audio_hash`, blob-agnostic), so a copy that differs only in its
  comment blob still matches. Byte-identical audio only; a re-encode at a different path is out of scope.
- Per-SOUND by design, never per-channel. A base spook the mod did NOT capture - dropped by dedup or the
  loudness cull, so it was never shipped - stays in its channel and still plays. The veto owns only what
  the director ships; the base keeps the rest, so a channel goes fully silent only when every sound in it
  is ours. This is deliberate (the base's own uncaptured atmosphere is not ours to remove), not a leak.
  Verified: `out_screams` removes 24 of its 25 base screams (exactly the captured ones), leaving `sound_13`
  (uncaptured) - which is the one the base still fires in the trace, at ear level, on top of the director.
- The generator scans every `sound_channels.ltx` across `VETO_CONFIG_ROOTS` (the GAMMA mods, the source
  packs, Anomaly), so a removal exists for whatever channel any install files our sound under. A channel
  absent from a given config is safely ignored by DLTX (warn-and-discard, no CTD, `Xr_ini.cpp:1383-1400`).
- Bed-empty guard: a channel that is a bed anywhere (System A asserts on empty `sounds`,
  `Environment_misc.cpp:108`) also gets `>sounds = ambient\no_sound`, so a full removal never leaves a
  bed empty. See "Muting a channel: the `ambient\no_sound` trick" in the ambient-sound-system note.
- TESTED-AGAINST baseline: Anomaly 1.5.3, GAMMA definition 920 (Soundscape Overhaul #3 + Dark Signal
  Weather and Ambiance #304 active), plus every pack under `anomaly_audio_mods`. The generated overlay
  self-documents its coverage in the file header - the scanned roots and every mod that actually played
  one of our sounds and was vetoed (e.g. Soundscape Overhaul 338, Dark Signal 304 -> 328). Re-run to
  refresh the list after any modlist change. The standalone builds under `stalker_versions_for_sound`
  are sound SOURCES, not play targets (AlifeSpooks does not run in them), so they need no veto.

The removal is on the sound's original path, matched to the base list item exactly (the engine removes
by exact string, `Xr_ini.cpp:1259-1263`), so the overlay emits each channel's path exactly as the
source config wrote it. No folder blocking, no mod names, no runtime lookup, no `provenance.tsv`.

### The observer hook (tracing only)

A separate time-event on the vanilla `update_ambient` slot (`update_ambient_owned`, installed by
`_apply_owned`) owns that slot ONLY to replay and LOG the base ambient - a clone of
`sound_ambient.update_ambient` (same channel rotation, timing, and volume rule, with added nil-guards),
except it replays through `xsound.play` (an engine-owned one-shot), so a base sound is not cut on channel
re-fire the way vanilla's retained-handle GC cut it. It does no muting (the composed config it reads already has our sounds
removed) and no injection; it exists so the base soundscape stays traceable at DEBUG (`[BASE]` / `[LOOP]`
lines and the HUD BASE row). If another script wins the slot back (e.g. TestZone's ambient logger), only
the trace is lost - the muting still holds because it is the static overlay, not this hook. This hook is
a separate slot from the director's `dread_director`; the two never share.

## Preservation and proof

- Audio is byte for byte, proven. `cmd_provenance` re-derives the deploy and compares each shipped
  file's audio hash to its source. The current build reports every shipped file matched, zero
  mismatch, comment-blob-agnostic so a written blob does not count as a change.
- Volume and distance sit in the X-Ray blob. A source file that shipped with a blob keeps it exact.
  A blob-less file gets the category-folder median, base_volume 1.0, which is an approximation and is
  booked as one, not counted as preserved.
- `provenance.tsv` (`cmd_provenance`) maps every shipped sound to its origin mod, directory,
  filename, source channel, that channel's distance and period settings, the deployed base_volume,
  and the original level:time:weather sections it played in. Nothing loses its origin under the
  index rename.
- `ledger.tsv` (`cmd_ledger`) hashes every source dark sound and books it: shipped, held, or
  excluded with a reason (emission-domain, intra-corpus re-encode, dead-silent, off-rate,
  off-scope). The invariant is `UNUSED-DARK = 0`. No net-new dark sound is left uncaptured.

## Invariants

- Performance first. Performance is the top priority and outranks features. A feature that cannot
  meet the budget is reworked, replaced, or removed with an X-Ray engine modification, never kept at
  the cost of the budget. Only correctness and never breaking base gameplay rank above it. See
  `doc/standards/code-standards.md`.
- Use the engine, don't work around it. Every capability comes from the engine and the Anomaly layer
  first, always through xlibs. Our own code enters only where stock behavior falls short.
- I1 One-shots only. The director fires every sound once through `xsound.play`. There is no loop
  layer and no continuous bed. A long sound plays on a long period, tuned to its measured duration.
- I2 No channels for our content. Sounds live in category directories and are named by the manifest.
  The deploy defines no `sound_channels.ltx` channels for our content; the only config it writes is the
  DLTX veto overlay, which REMOVES our sounds from existing base channels and never adds one. The engine
  ambient bed and its asserted channels stay intact, so nothing can cause a missing-channel crash.
- I3 Deduplicate by the waveform, source side only. md5 then Chromaprint fingerprint then PCM
  cross-correlation, complete linkage at 0.90. Distinct variety is never merged. Deduplication runs
  among the source packs, never against the target modpack.
- I4 Fitness is codec plus sample rate: 44100 Hz vorbis. Off-spec files are dropped and accounted.
- I5 Ship byte for byte. The audio pages are the file's own, untouched; only the X-Ray blob is rewritten
  losslessly. Distance (min/max) is the source's own (a blob-less file gets the category band); base_volume
  is leveled for every file to the corpus-median loudness (`_normalize_blobs`), not the source's authored
  value. The one exception is a file that must
  be transformed to fit the one-shot model: a `dark_signal` bed too long for the emission tick is sliced
  into desilenced pieces, which re-encode and so lose the source blob (booked "cut", category-median blob).
- I6 Capture from folder trees, not just wired files. The ledger proof is what drives UNUSED-DARK to
  0.
- I7 Selection is manual and per-pack. A pack's folders are mapped to categories by hand in
  `ROUTE` after the pack is assessed. The folder-path match only pulls.
- I8 Remove, do not inject. The static DLTX overlay removes a base sound the mod ships from its
  channel, matched by audio identity, per item. It never adds a channel and never injects a sound into
  the base ambient. The base's other sounds are untouched.
- I9 Dark scope only. Keep spook, horror, underground, eerie, and oppressive weather. Leave generic
  daytime life and the base weather bed to the base ambience.
- I10 Leave emission alone. Blowout and psi-storm are their own system and are never touched.
- I11 Reproducible. plan to classify to loudness to deploy to ledger to provenance regenerates the
  whole overlay from the packs.
- I12 Traceable. Every shipped sound resolves to its origin via `provenance.tsv`. Every source file
  resolves to a ledger category. Credit every source pack, author and link, in the readme.
- I13 The director owns its own play slot only while active. Without xlibs the director is inert (no
  play), but the veto still holds - it is the static DLTX overlay, independent of xlibs. The observer
  clone resets on hour, level, or weather change, so it never replays a channel for the wrong level, and
  it guards every value an engine call needs.

## MCM and trace

Scripts add control, an in-game trace, and the MCM, mirroring the alife-family pattern (`as_mcm`,
`as_debug`, `xmcm`, `xlog`). All are guarded. Without xlibs they degrade to no-ops.

- `as_director.script` owns the director (its own `dread_director` slot), the score, the pick and pace,
  the positioned play, and the base-ambient observer (the separate `update_ambient` slot; the muting
  itself is the static DLTX overlay the deploy generates).
- `as_hud.script` is the debug HUD (off by default), a three-column readout built from
  `as_director.get_hud_rows`.
- `ui_as_player_tab.script` + `pda_dynamic_tabs.script` are the dev PDA tab (gated by the MCM `dev_tab`
  toggle): a runtime-injected tab (the demonized `build_extra_tabs` + `pda.set_active_subdialog` hook, no
  `pda_16.xml` override) that browses `zs/<category>/` off disk and auditions each sound through the
  director's own `emit` at at-ear / a set distance / the exact director curve, plus an inspector (spot
  readout, a note box, the n114 Beacon, and a Snapshot that calls `as_test.snapshot`). INSERT opens the PDA
  straight to it (`open_tab`), deferred through a shown-gated game TimeEvent so the list builds only once
  the PDA is actually on screen - filling it during the 3D-PDA draw hits a detached list box and CTDs in
  `CUIScrollView::Clear`. The tab window is NOT `SetAutoDelete` (the vanilla radio/taskboard pattern):
  `get_ui` caches it in a singleton, so letting the engine free it would feed the PDA a dangling window and
  CTD in `CUIStatic::Update`. The old `as_test` INSERT note box is retired - this inspector supersedes it.
- `as_debug.script` is the trace facade. At DEBUG it records every sound played and every term of the
  dread score to `alifespooks.log`, so the soundscape is checked by observation. Below DEBUG the off
  path marshals nothing and crosses no luabind bridge.
- `as_mcm.script` is one MCM page tree. Atmosphere holds a single master volume for our sounds (no
  per-category sliders). Visuals toggles the peak-dread screen distortion. Development holds the trace
  level, a log flush, the debug HUD position, and a reset-to-defaults button. Every control is neutral
  at its default. Labels in English and Russian.

## Tools and data artifacts

- Signal analysis: `ffmpeg` (`aspectralstats` centroid and flatness, `astats` crest, `ebur128`
  loudness), `ffprobe` (duration, rate, codec). Dedup identity: md5, then Chromaprint `fpcalc`, then
  PCM cross-correlation. Resolved from `$PORTX_ROOT/packages` by `soundpool.py`.
- Committed data: `merged_channels.json` (the curated corpus per category), `classification.json`
  (measured features), `loudness_outliers.json`, `folder_audit.tsv` (which source folders each category
  pulled), `ledger.tsv` (coverage proof), `provenance.tsv` (origin of every shipped sound).
- `merge.py` is the pipeline; its `MODS` list and `route`/`ROUTE` table are the source of truth. The
  whole run is one command, `merge.py all` (plan -> classify -> loudness -> deploy -> ledger ->
  provenance, in order). `soundpool.py` is the probe and resolver.

Adopting a pack: assess it by hand, add it to `MODS` and its folder rules to `ROUTE`, re-run
`merge.py all`, read the ledger (UNUSED-DARK must stay 0) and the provenance self-verify (0 mismatch).

## Deploy

A gamedata overlay distributed as a GitHub release and moddb addon. The repo holds the buildable
source, the tool, the docs, and the audio. Wired for local sync and the gamma-redux install through
`stalker-manager`.
