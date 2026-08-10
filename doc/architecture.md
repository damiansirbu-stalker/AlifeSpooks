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
- The engine ambient system is left untouched, with one exception: the director owns the vanilla
  `update_ambient` slot to mute the base's own copy of a sound we ship (the veto, below).

Because the director is the only playback path, xlibs (`xsound`) is required. Without it the mod is
inert: no sound plays and the veto does not run.

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
deploy      audio + manifest + veto data             -> gamedata/
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
- deploy (`cmd_deploy`): copy each sound byte for byte to `zs/<category>/<n>.ogg`, write the X-Ray
  attenuation blob into blob-less files, and write the two data files the director reads, the sound
  manifest and the base-veto set (`as_blockdata.script`).
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
plays it. Doubling with the base is handled at runtime by the veto.

## Verbatim audio and per-file distance

Every kept sound ships byte for byte. No re-encode. Each file carries its own play settings two ways:

- The X-Ray ogg comment blob (min distance, max distance, base_volume). A source file that already
  carries a blob keeps it exactly, since the audio is byte-copied and the blob is never rewritten.
  The engine reads that blob at play and applies the source's attenuation and base volume.
- A source file with no blob is given one losslessly (`_band_blobs`): the median min and max of its
  category-folder members that do carry a blob, with base_volume 1.0. Only the comment header page
  changes and the audio pages stay byte-identical. This is an approximation from folder peers, not a
  recovered original, and is recorded as such.

The manifest carries each sound's min distance, max distance, and height, inherited from its source
channel settings, so the director can position the sound before the engine applies the blob.

Fitness gate: 44100 Hz vorbis only, the X-Ray standard. Off-rate and junk-bitrate files are dropped
and accounted, never silently.

## The director

The director conducts playback from a cached read of live context. It scores the dread of the
player's surroundings, and the score decides which categories are eligible, how often a sound fires,
how close it plays, and how loud. Context is read on a throttled tick (`CTX_PERIOD`, about 3s) and
cached. The play path reads the cache. The enclosure raycast is cached by a coarse position cell and
re-fires only when the player changes cell. Nothing runs per frame.

Dread is a scalar 0..1 built from four reads (`_score`):

- Place. The nearest smart terrain keys `as_smart_lore.ltx` for a class (safe, den, psy, lab, ruin,
  eerie, mundane) hand-curated from the smart props, the location names, and canon. A smart out of
  range or unlisted falls to a per-level baseline. This is the dread a place carries on its own.
- Faction. The place's owning faction is read from the smart's declared factions and checked against
  the player's own community through `game_relations.is_factions_enemies`. Allied ground reads as a
  refuge, enemy ground raises dread, and it is correct whatever faction the player runs.
- Presence. The online creature set within range, read live from `db.storage`, not a smart's roster.
  Enemies raise dread, a horror-tier mutant raises it and opens the growl category, allies ease it.
  Trash-tier mutants never count.
- Safety. The one cutout to calm: allies present, in daylight, with no threat near. Everything off
  that cutout keeps at least a low floor, so a friendly held base is the only true refuge and the
  Zone is never dead quiet where it should not be.

Selection and pacing:

- Categories are the fixed palette (`CATEGORIES`), each with a firing gate and a rarity floor.
  spook, scream, and drone play wherever dread is up. growl needs a real mutant near. underground and
  machine play on an actual underground level, read from the engine `underground` flag. gunfire
  plays outdoors where a human is present. creak, wind, and wildlife play everywhere as texture.
- `_pick_category` is weighted-random among the eligible categories. The weight rises with dread for
  the dread categories and with calm for the texture categories, with a recent-category penalty so
  scares do not repeat back to back.
- `_pick_sound` keeps a per-category ring of recent picks and re-rolls until a fresh one, so a sound
  never plays twice in a row. The window is capped below the category's sound count so the pick
  always terminates.
- `_play` positions the sound at a distance interpolated from its min and max by the dread score, so
  a scary place brings the sound closer and louder, and scales by the MCM distance and volume knobs.
- Emission is a per-tick probabilistic roll, not a scheduled interval. Each tick the director computes
  the dread and decides whether to emit. The per-tick probability is set so the average rate matches
  the measured classical spook cadence (`as_manifest.cadence_ms`, the vanilla and Dark Signal
  Amplified average of how often the base ambient plays a spook, faster than a single channel because
  several run per section), scaled up with dread and down with the MCM rarity knob, then decided by a
  random roll so it never fires like clockwork. An active firefight mutes the director, since a subtle
  scare is lost under gunfire.

Visual layer: at the top dread grade only, a short distortion pulse fires occasionally through xlibs
`xpp`, dwell-gated so a momentary spike never flashes, on a cooldown, muted during combat.

## The base-veto: mute the source pack's copy, do not inject

If the player also runs a source pack AlifeSpooks pulled from, that pack's ambient config plays the
same spook sounds. The director owns the vanilla `update_ambient` slot and runs a faithful clone of
it (`update_ambient_owned`), with one change: a base sound the mod also ships is dropped at load, so
only the director plays it. The base's other ambient plays untouched. There is no enrichment of a
base channel and no injection. The mod suppresses a base play, it never adds one.

The match is on the sound's original relative path, since the base references its sounds by path. The
deploy writes the path set the veto needs to `as_blockdata.script`:

- `blockfiles`: the exact original path of every sound we ship.
- `blockdirs`: the source folders we drew from, matched against a base sound's own parent directory,
  so a base sound in a folder we own is muted even when we did not pick that exact file.

The set holds game sound paths only, no mod names. It is derived from the shipped corpus at deploy
time and read at runtime by `_build_block`. It never reads `provenance.tsv`.

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
  The deploy writes no `sound_channels.ltx` definitions for our content. The engine ambient bed and
  its asserted channels stay intact, so nothing can cause a missing-channel crash.
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
- I8 Mute, do not inject. The veto suppresses a base sound the mod ships, matched by original path.
  It never adds a channel and never injects a sound into the base ambient.
- I9 Dark scope only. Keep dread, horror, underground, eerie, and oppressive weather. Leave generic
  daytime life and the base weather bed to the base ambience.
- I10 Leave emission alone. Blowout and psi-storm are their own system and are never touched.
- I11 Reproducible. plan to classify to loudness to deploy to ledger to provenance regenerates the
  whole overlay from the packs.
- I12 Traceable. Every shipped sound resolves to its origin via `provenance.tsv`. Every source file
  resolves to a ledger category. Credit every source pack, author and link, in the readme.
- I13 The director owns the play slot only while active. Without xlibs it is inert, no play and no
  veto. The clone resets on hour, level, or weather change, so a sound never fires on the wrong
  level, and it guards every value an engine call needs.

## MCM and trace

Scripts add control, an in-game trace, and the MCM, mirroring the alife-family pattern (`as_mcm`,
`as_debug`, `xmcm`, `xlog`). All are guarded. Without xlibs they degrade to no-ops.

- `as_effect.script` owns the director, the pick and pace, the positioned play, and the base-veto.
- `as_debug.script` is the trace facade. At DEBUG it records every sound played and every term of the
  dread score to `alifespooks.log`, so the soundscape is checked by observation. Below DEBUG the off
  path marshals nothing and crosses no luabind bridge.
- `as_mcm.script` is one MCM page tree with three tabs. Atmosphere holds an overall volume, spook
  sensitivity, rarity, distance, and one per-category volume slider per director category (drone,
  spook, scream, growl, machine, gunfire, underground, creak, wind_creep, animals), read by the
  director into `_cat_vol` and applied in `_play`. Visuals toggles the peak-dread screen distortion.
  Development holds the trace level, a log flush, the debug HUD, and a reset-to-defaults button. Every
  control is neutral at its default. Labels in English and Russian.

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
