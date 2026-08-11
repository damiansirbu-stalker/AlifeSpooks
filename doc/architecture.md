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
- The director (`gamedata/scripts/as_effect.script`) plays each sound as a positioned one-shot
  through `xsound.play`. There are no loops and no continuous beds. A long horror drone or a psy bed
  plays as a one-shot on a long period, not as a continuous loop.
- The base's own copy of a sound we ship is removed from its ambient channels statically by a DLTX
  overlay at config load (the veto, below), so the base never doubles the director. A separate observer
  owns the vanilla `update_ambient` slot only to replay and log the base ambient.

Because the director is the only playback path, xlibs (`xsound`) is required. Without it the mod is
inert: no sound plays.

The category is the unit of organization and of play. It is a directory of sounds, a firing gate,
and a rarity floor. The director reads a generated manifest (`as_manifest.script`) that lists each
category, its sounds, and each sound's distance and height. The manifest replaces the channel
definitions the director used to read from `sound_channels.ltx`. Anomaly Lua cannot enumerate a
directory at runtime, so the deploy writes the manifest and the director reads it.

## Content pipeline (reproducible)

`tools/merge.py` is a six-stage pipeline. Each stage is a subcommand that reads the previous stage's
committed artifact and writes the next. Adopting a pack is a re-run, not a rewrite.

```
plan        source trees, deduped by waveform        -> merged_channels.json
classify    measured features per sound              -> classification.json
loudness    per-group loudness, outliers flagged     -> loudness_outliers.json
deploy      audio + manifest + veto DLTX overlay     -> gamedata/
ledger      content-hash proof of coverage           -> ledger.tsv
provenance  every shipped sound -> its origin         -> provenance.tsv
```

- plan (`cmd_plan`): pool the dark sounds from each source pack two ways, from the pack's own config
  lists (`DARK_KEEP`) and by walking its folder trees (`DARK_FILL`), because a pack ships far more
  dark content than it wires. Resolve, gate on codec and sample rate, drop dead-silent files, then
  deduplicate by waveform. Output `merged_channels.json`, the curated dark corpus.
- classify (`cmd_classify`): one ffmpeg pass per sound for duration, spectral centroid and flatness,
  and crest. The measured duration drives the deployed period so a long sound does not overlap
  itself. There is no loop-versus-effect decision. Everything is a one-shot.
- loudness (`cmd_loudness`): measure integrated loudness per sound and flag per-group outliers.
- deploy (`cmd_deploy`): measure each source's peak and CULL the near-silent (`_loudness_cull`), copy
  the survivors byte for byte to `zs/<category>/<n>.ogg`, write each file's blob with source attenuation
  plus a loudness-normalizing base_volume (`_normalize_blobs`), write the sound manifest the director
  reads (`as_manifest.script`), and generate the base-veto DLTX overlay that removes our sounds from the
  base ambient channels (`_veto_dltx` -> `mod_sound_channels_alifespooks.ltx`).
- ledger (`cmd_ledger`) and provenance (`cmd_provenance`): the proofs, below.

### Selection is manual, pulling is mechanical

Which packs and which folders contribute is a per-pack judgment, made by hand before any pull. Each
new pack is opened and assessed for what dark content it actually holds, and its folders are mapped
to categories by adding rows to `DARK_FILL`. The folder-substring match in `DARK_FILL` is only the
mechanical pull that runs after that decision. There is no keyword classifier that decides scope on
its own. The `UNUSED-DARK = 0` ledger invariant then confirms the hand-written rules captured every
dark file the pack holds.

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

## Verbatim audio, loudness-normalized blob

Every kept sound's AUDIO ships byte for byte - no re-encode, the vorbis pages are untouched. What the
deploy writes is only the X-Ray ogg comment blob (min distance, max distance, base_volume), a lossless
header-page rewrite (`_write_blob`); the audio pages stay byte-identical.

- **Attenuation** (min/max distance) is the source's. A file that carried a source blob keeps its
  min/max; a blob-less file gets the median min/max of its category-folder peers.
- **Loudness is normalized via base_volume** (`_normalize_blobs`, `TARGET_PEAK_DB`). base_volume is a
  linear multiplier the engine applies on every play (see `sound-source-and-emitter.md`), so setting it
  per file to `10^((-1 dB - measured_peak)/20)` peak-normalizes every sound to ~-1 dB without touching
  the samples. This reinstates the loudness leveling n107 removed - the RIGHT way this time (n014's
  ffmpeg re-encode was destroying the blob; the blob edit does not). Reference target is Dark Signal
  Amplified (Shrike), whose ambient median peak is ~-1 dB.
- **Loudness cull** (`_loudness_cull`, `CULL_PEAK_DB`): a file whose measured peak is below -30 dB
  cannot reach target without absurd gain (that is amplified noise, not a quiet sound), so it is DROPPED,
  not shipped. The older `_silence_gate` (drops only true -inf) still runs first. No near-silent file
  survives - a distant/faint feel comes from the director's POSITIONING, never from a quiet source file.

The manifest carries each sound's min distance, max distance, and height, inherited from its source
channel settings, so the director can position the sound before the engine applies the blob.

Fitness gate: 44100 Hz vorbis only, the X-Ray standard. Off-rate and junk-bitrate files are dropped
and accounted, never silently.

## The director

The director runs on its OWN time-event, `("as_effect","dread_director")` - a private slot nothing
else contends for, self-rescheduling every second (`_director_tick`). It is entirely separate from the
base-ambient observer (below), which owns the vanilla `update_ambient` slot; the two never share a slot. Each tick
the director refreshes the cached dread score (every `CTX_PERIOD`, about 3s) and runs the emission. The
enclosure raycast is cached by a coarse position cell and re-fires only when the player changes cell.
Nothing runs per frame.

### The dread score

Dread is a scalar 0..1, purely additive - no multipliers, no floor constant (`_score`):

    dread = lore + who's-around + indoor + time

- **lore** - the place's own dread, by class. The nearest smart terrain (within `PLACE_RADIUS`) keys
  `as_smart_lore.ltx` for a class: mundane 0.10, eerie/ruin 0.25, den/lab 0.40, psy 0.50 - hand-curated
  from the smart names and canon. Out of range or unlisted falls to a per-level baseline. The primary
  driver: a place either is or is not spooky.
- **who's-around** - ONE categorical state, not a per-body tally: `allied` -0.15, `alone` +0.10,
  `enemy` +0.18, `mutant` +0.22, `mixed` +0.25. Read live from `db.storage` within `PLACE_RADIUS`;
  the `enemy` state folds in enemy-held ground, so an empty enemy base still reads hostile
  (`_ownership`). Being among allies is the only calming state; alone / enemy / mutant all sit above
  zero, so the Zone's baseline uneasiness emerges from the state itself - there is no separate floor.
  Count and proximity do NOT scale it: this is atmosphere, not a threat alarm.
- **indoor** +0.15 - enclosed, from the `xcombat.is_indoor` roof+wall raycast OR the smart's surge
  shelter.
- **time** - a few discrete stages, not a curve: day 0, dawn/dusk +0.04/+0.06, night +0.10, deep
  night +0.12.

No cutout, no floor: the score is a pure sum. Being among allies is the only negative term
(`WHO_DREAD.allied`), so a calm place with your own people falls below the `DREAD_ON` floor on its own
(a friendly base by day is silent), while a genuinely scary place still carries its lore through. The
score maps to a grade on wide boundaries - NONE < 0.20, LOW 0.20, MED 0.40, HIGH 0.60, INSANE 0.80 - so
the range discriminates instead of clamping everything to the top. Mutants are the one signal that feeds
BOTH the score (the `mutant`/`mixed` state) and the TYPE (they gate the growl category).

### Selection, pacing, and positioning

- Category (the TYPE) is chosen by a context gate: `growl` needs a mutant near, `machine`/`underground`
  need an underground level (engine `underground` flag), `gunfire` needs a human near outdoors, the
  rest (`spook`, `drone`, `scream`, `creak`, `wind`, `animals`) play anywhere. `_pick_category` is
  weighted-random among the eligible, weight rising with dread for the spook categories and with calm
  for texture, with a recent-category penalty.
- `_pick_sound` is a shuffle-bag: every sound in a category plays once before any repeat.
- Emission is a jittered self-reschedule, NOT a per-tick roll: after each fire the next play is armed
  at `math.random(SPACE_MIN_MS, SPACE_MAX_MS)` (5-15s, scaled by the MCM rarity knob). Density is
  constant and dread-INDEPENDENT; dread drives SELECTION and closeness, never the rate. Below `DREAD_ON`
  (0.20) nothing plays.
- `_play` positions each one-shot with Anomaly's OWN geometry (`sound_ambient.script:127-141`): a
  random point in the sound's source min..max band, halved, at a random angle, at the source height.
  The one change is `HORROR_PULL` - at peak dread it lands up to 25% closer. The attenuation (the
  source's baked min/max) is left to the engine, so a near sound is full and fades naturally; the max
  is NEVER used as the spawn position.

Visual layer: at the top dread grade only, a short distortion pulse fires occasionally through xlibs
`xpp`, dwell-gated so a momentary spike never flashes, on a cooldown.

### Debug HUD (`as_hud`, off by default)

A three-column readout (MCM `hud_position`) with the dread palette - gold section headers, off-white
body: SPOOK (the director's current one-shot on its own row, bright while sounding and gray once
stopped), BASE directly under it and symmetrical (the sound the base-ambient observer is replaying, same
treatment - muting is the static overlay, so there is no tally), AVAILABLE (a wrapped comma list of the
categories eligible now), SENSORS (one harmonized block: the dread terms with their contribution, then
the type-gate reads), and the DREAD summary - the summed score and grade, the row tinted green->red by
severity. Players never see it; it feeds off `as_effect.get_hud_rows`.

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
- The generator scans every `sound_channels.ltx` across `VETO_CONFIG_ROOTS` (the GAMMA mods, the source
  packs, Anomaly), so a removal exists for whatever channel any install files our sound under. A channel
  absent from a given config is safely ignored by DLTX (warn-and-discard, no CTD, `Xr_ini.cpp:1383-1400`).
- Bed-empty guard: a channel that is a bed anywhere (System A asserts on empty `sounds`,
  `Environment_misc.cpp:108`) also gets `>sounds = ambient\no_sound`, so a full removal never leaves a
  bed empty. See "Muting a channel: the `ambient\no_sound` trick" in the ambient-sound-system note.

The removal is on the sound's original path, matched to the base list item exactly (the engine removes
by exact string, `Xr_ini.cpp:1259-1263`), so the overlay emits each channel's path verbatim as the
source config wrote it. No folder blocking, no mod names, no runtime lookup, no `provenance.tsv`.

### The observer hook (tracing only)

A separate time-event on the vanilla `update_ambient` slot (`update_ambient_owned`, installed by
`_apply_owned`) owns that slot ONLY to replay and LOG the base ambient - a faithful clone of
`sound_ambient.update_ambient`. It does no muting (the composed config it reads already has our sounds
removed) and no injection; it exists so the base soundscape stays traceable at DEBUG (`[BASE]` / `[LOOP]`
lines and the HUD BASE row). If another script wins the slot back (e.g. TestZone's ambient logger), only
the trace is lost - the muting still holds because it is the static overlay, not this hook. This hook is
a separate slot from the director's `dread_director`; the two never share.

## Preservation and proof

- Audio is byte for byte, proven. `cmd_provenance` re-derives the deploy and compares each shipped
  file's audio hash to its source. The current build reports every shipped file matched, zero
  mismatch, comment-blob-agnostic so a written blob does not count as a change.
- Volume and distance ride in the X-Ray blob. A source file that shipped with a blob keeps it exact.
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
- I5 Ship byte for byte. Per-file volume and distance are the file's own X-Ray blob. A blob-less file
  gets a category-band blob written losslessly, base_volume 1.0.
- I6 Capture from folder trees, not just wired files. The ledger proof is what drives UNUSED-DARK to
  0.
- I7 Selection is manual and per-pack. A pack's folders are mapped to categories by hand in
  `DARK_FILL` after the pack is assessed. The substring match only pulls.
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

- `as_effect.script` owns the director (its own `dread_director` slot), the score, the pick and pace,
  the positioned play, and the base-ambient observer (the separate `update_ambient` slot; the muting
  itself is the static DLTX overlay the deploy generates).
- `as_hud.script` is the debug HUD (off by default), a three-column readout built from
  `as_effect.get_hud_rows`.
- `as_debug.script` is the trace facade. At DEBUG it records every sound played and every term of the
  dread score to `alifespooks.log`, so the soundscape is checked by observation. Below DEBUG the off
  path marshals nothing and crosses no luabind bridge.
- `as_mcm.script` is one MCM page tree with three tabs. Atmosphere holds an overall volume, rarity,
  distance, and one per-category volume slider per director category (drone, spook, scream, growl,
  machine, gunfire, underground, creak, wind_creep, animals), read by the director into `_cat_vol` and
  applied in `_play`. Visuals toggles the peak-dread screen distortion. Development holds the trace
  level, a log flush, the debug HUD position, and a reset-to-defaults button. Every control is neutral
  at its default. Labels in English and Russian.

## Tools and data artifacts

- Signal analysis: `ffmpeg` (`aspectralstats` centroid and flatness, `astats` crest, `ebur128`
  loudness), `ffprobe` (duration, rate, codec). Dedup identity: md5, then Chromaprint `fpcalc`, then
  PCM cross-correlation. Resolved from `$PORTX_ROOT/packages` by `soundpool.py`.
- Committed data: `merged_channels.json` (pool plus per-channel source settings), `classification.json`
  (measured features), `loudness_outliers.json`, `ledger.tsv` (coverage proof), `provenance.tsv`
  (origin of every shipped sound).
- `merge.py` is the pipeline, its `MODS` list is the source of truth. `soundpool.py` is the
  probe and resolver.

Adopting a pack: assess it by hand, add it to `MODS` and its folder rules to `DARK_FILL`, re-run the
pipeline, read the ledger (UNUSED-DARK must stay 0) and the provenance self-verify (0 mismatch).

## Deploy

A gamedata overlay distributed as a GitHub release and moddb addon. The repo holds the buildable
source, the tool, the docs, and the audio. Wired for local sync and the gamma-redux install through
`stalker-manager`.
