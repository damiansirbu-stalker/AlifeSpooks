#!/usr/bin/env python3
"""Channel-driven merge for the Zone Soundscape override.

Uses each mod's own sound_channels.ltx as the curation signal: a sound "belongs"
in a channel because some mod put it there. For each channel (union of names), it
pools every sound any mod assigns to it, dedups identical sounds by fingerprint,
and keeps the best-quality copy. Channel settings (distance/period) come from the
highest-priority mod that defines the channel.

    plan   -> merged_channels.json + a report (no deploy)

Presets and the LTX/sound emit into GammaOverrides come in the next steps.
"""
import sys, json, re, collections, hashlib, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import soundpool as sp

LOWQ_BITRATE = 32000  # drop clearly junk-bitrate files when a category has better

# The CATEGORY list - the shipped folders (zs/<name>) and the manifest keys. The pipeline ONLY captures
# and organizes: `route` (below) maps each source file to one of these by folder path. It carries NO
# play rules - env, presence gates, map-eligibility and enclosure filters are RUNTIME selection, owned by
# as_director + the per-map LTX, never baked here. Ordered for the report/audit; `mutant` is one pooled bag.
CATEGORIES = [
    "mutant",
    "mutant_ambient_forest", "mutant_ambient_swamp", "mutant_ambient_urban", "mutant_ambient_field",
    "spook", "scream", "drone", "dark_signal",
    "industrial", "structural", "labs", "drip",
    "wind", "foliage", "wildlife", "urban", "gunfire", "rats", "bats",
]

# Out-of-scope / misfiled source paths to skip (n109). psi-storm is emission-domain (readme: "does not
# touch emission or psi-storm sound"); giant_underground is a monster roar misfiled into an ambient tree;
# ambience_exp is the Immersive Ambience Expansion weather tree (silent drip, non-dread wind - user-checked).
EXCLUDE = ("psi_storm", "psistorm", "giant_underground", "ambience_exp",
           "music", "soundtrack")   # NO MUSIC: music/, soundtrack/, dyn_music/, **/music, radio_music, megafon/music

# Zone terrains for the map-selected mutant_ambient_<zone> categories (n117: forest/swamp/urban/field).
ZONES = ("forest", "swamp", "urban", "field")
# Creature-pool keep filter: from a monsters/<species> or soundscape/mutants/<species> tree, keep only
# the near-lurking AMBIENT dread (idle/growl/ambient_drone/eat/distant/moan/breath). Combat sounds
# (attack/hit/die/pain/step) are dropped - fired ambiently with no creature present they play out of
# context. The gate is a single boolean, so species is preserved in provenance only, not a subfolder.
MUTANT_KEEP = re.compile(r"(idle|growl|ambient_drone|_eat|distant|moan|breath|lurk)", re.I)

# STRUCTURAL per-file allowlist (n117): first matching substring maps a source path to a category. Ordered
# specific-first. Whole-tree capture, not keyword matching. Anything unmatched is DROPPED (dark scope, I9).
# Weather (storm/rain/thunder/pre_storm/tuman) and generic life (birds/bugs/insects/frogs) are left out.
ROUTE = [
    ("unused interior", "structural"),                          # Shrike's granted interior pack (slam + interior winds), all indoor
    ("/screams", "scream"),
    ("/dark_signal", "dark_signal"), ("radio/white_noise", "dark_signal"),   # the 4-min radio static bed
    # spooks_below/<sub> (the packs nest this under .../soundscape/underground/, so the sub-tree is the
    # discriminator, NOT the container folder). Specific first, so vermin/water/creaks win over labs.
    ("spooks_below/rats", "rats"),
    ("spooks_below/bats", "bats"),
    ("spooks_below/water_drip", "drip"), ("spooks_below/drip", "drip"),
    ("spooks_below/creaks", "structural"),
    ("spooks_below/drone", "drone"),
    ("spooks_below/lab", "labs"), ("spooks_below/machine", "labs"), ("spooks_below/metal", "labs"),
    ("spooks_below/noise", "labs"), ("spooks_below/banging", "labs"), ("spooks_below/ambient", "labs"),
    ("spooks_below/background", "labs"), ("spooks_below/lowrumble", "labs"), ("spooks_below/lowchancerumble", "labs"),
    ("spooks_below/spooks", "spook"),
    # spooks_above/<sub> (surface, also under the underground container in some packs)
    ("spooks_above/drone", "drone"),
    ("spooks_above/spooks", "spook"),
    # other trees for the same kinds
    ("water_drip", "drip"), ("/drip", "drip"),
    ("nature/bats", "bats"),
    ("/creak", "structural"),
    ("device/airtight", "structural"), ("device/door", "structural"),
    ("device/metal_small", "structural"), ("device/old/door", "structural"),
    ("out_drone", "drone"),
    ("urban_drones", "industrial"), ("day_drones", "industrial"), ("/drones", "industrial"),
    ("urban_spoops", "urban"), ("urban_debris", "urban"), ("ambienturban", "urban"),
    # dread wind ONLY (creep/dark/gale/heavy/strong); generic/forest/normal/gust/storm/rain left out
    ("wind_dark", "wind"), ("wind_creep", "wind"), ("wind_gale", "wind"), ("wind_heavy", "wind"),
    ("wind_strong", "wind"), ("spookgust", "wind"), ("galewind", "wind"), ("windwhistle", "wind"),
    ("creepy_low_wind", "wind"),
    ("foliage_spook", "foliage"), ("/branch", "foliage"), ("tree_sway_fog", "foliage"), ("/rustle", "foliage"),
    ("soundscape/foliage", "foliage"),
    ("crow/", "wildlife"), ("crows/", "wildlife"), ("owl/", "wildlife"), ("owls/", "wildlife"),
    ("dog/", "wildlife"), ("dogs/", "wildlife"),
    ("/shooting", "gunfire"), ("out_gunfire", "gunfire"),
    # generic surface spook (whispers, spoops, amb_dark/night)
    ("/spooks/", "spook"), ("northern_spoops", "spook"), ("northen_spoops", "spook"), ("_spoops", "spook"),
    ("whisper", "spook"),
    ("amb_dark", "spook"), ("amb_night", "spook"),
    ("spooks_above", "spook"),
    # standalone underground trees -> labs, LAST (spooks_above/below already routed above; this catches the
    # loose ambient/underground, soundscape/underground/under_NN, ugrnd, x18/x16 files with no sub-tag)
    ("ugrnd_", "labs"), ("/ugrnd/", "labs"), ("/x18", "labs"), ("/x16", "labs"),
    ("ambient/underground/", "labs"), ("soundscape/underground/", "labs"), ("underground_", "labs"),
    # standalone/spinoff old-build dread trees (SoC-lineage builds; x18/x16/ugrnd already routed above).
    # NOTE: no /anomaly/ rule - the SoC anomaly/ tree is the full anomaly SFX set (activation/burst/hit),
    # not dread ambient, and anomaly/blowout is its own system (I10). drone stays the spooks_*/drone hums.
    ("metro_horror", "dark_signal"),                            # Lost-Alpha walkie-talkie radio horror
    ("/horror/", "spook"), ("hotel_horror", "spook"), ("/inferno/", "spook"),
    ("fear_sound", "spook"),                                    # NLC fear_sounds/<level>, Prosector pripyat fear
    ("night_scream", "scream"), ("fallscream", "scream"),
    ("rnd_horror", "spook"),
    ("iron_moan", "structural"), ("organic_moan", "spook"), ("org_moan", "spook"), ("rnd_moan", "spook"),
    ("wounded_psy", "spook"), ("psy_blackout", "spook"), ("psy_noise", "spook"), ("psy_voices", "spook"),
    ("ghost", "spook"),
    ("ambient/tuman", "spook"),                                 # fog night dread (whole tree)
    # rnd_outdoor distant-cue tokens (mixed folder; route by filename, not the whole folder).
    ("rnd_shooting", "gunfire"), ("fog_shooting", "gunfire"), ("distantmortar", "gunfire"),
    ("rnd_mutant", "mutant"), ("ambient_mutant", "mutant"), ("rnd_growl", "mutant"), ("distant_growl", "mutant"),
    ("rnd_howling", "wildlife"), ("outside_howl", "wildlife"), ("wolfhowl", "wildlife"),
    ("metal_noise", "structural"),
    ("ambient/special", "spook"),                               # SoC special dread ambience (psy/fear/scream)
    # Dead Air's Lost Alpha (lar_) borrowed ambience, by subfolder (metro_horror already -> dark_signal above).
    ("lar_indoor", "structural"), ("lar_war", "spook"), ("lar_suspense", "spook"), ("lar_ghosts", "spook"),
    ("lar_call", "spook"), ("lar_howled", "wildlife"),
    ("metro_swamp", "spook"), ("metro_tunnels", "labs"), ("metro_ambients", "labs"),
    ("lar_crow", "wildlife"), ("lar_dog", "wildlife"), ("lar_owls", "wildlife"),
    ("lar_wolf", "wildlife"),                                   # lar_frog / lar_pigeon left out - generic pond/bird, not horror
    ("lar_tree", "foliage"), ("lar_wind", "wind"),
    ("howling_wind", "wind"), ("howling", "wildlife"),         # wind-first so howling_wind != animal howl
]


def route(path):
    """Structural per-file category routing (n117): a source path -> a category name, or None to drop.
    Whole-tree allowlist by folder, not keyword matching on the filename. Order: exclusions, zone-mutant
    ambience, the creature pool, then the flat ambience allowlist (first match wins)."""
    low = path.replace("\\", "/").lower()
    if any(x in low for x in EXCLUDE):
        return None
    # zone-mutant ambience: ONLY the terrain-split trx/spooks_above/<zone>{day,night}mutants (validated
    # horror). The soundscape/background/<Terrain> beds were user-checked and rejected (birds/generic, no
    # horror), so they are NOT routed here - the zones are pure zone-mutant content.
    for z in ZONES:
        if z + "daymutants" in low or z + "nightmutants" in low:
            return "mutant_ambient_" + z
    # creature pool. wolf/mwolf are eerie wildlife, not creatures - BUT monsters/mwolf mixes in NPC COMBAT
    # vocalizations (wolf_attack/death/hit), which must NOT play as random ambience, so the same MUTANT_KEEP
    # combat filter applies: keep idle/distant/growl/etc. as wildlife, drop the attack/hit/die. soundscape/
    # mutants and the flat spooks_above/mutants are ALREADY ambient/distant dread (named sound_NN), no filter.
    if "/wolf/" in low or "/mwolf/" in low:
        return "wildlife" if MUTANT_KEEP.search(low) else None
    if "/monsters/" in low:
        return "mutant" if MUTANT_KEEP.search(low) else None
    if "/soundscape/mutants/" in low or "spooks_above/mutants" in low:
        return "mutant"
    return next((c for sub, c in ROUTE if sub in low), None)

# Source packs come from the REGISTRY in sources.py (n124): one declarative entry per pack with its download
# url + licence, so a build is reproducible and every shipped sound traces to a recorded source. Capture is
# still STRUCTURAL per-file (ROUTE, below): each pack's folder trees map to categories by path, the whole
# horror tree pulled, not just the channel-wired files. Registry ORDER is preserved (dedup is order-sensitive,
# so the order is load-bearing). `build.py provision` fetches any missing source from its url before a build.
import sources
MODS = sources.mods()

HERE = Path(__file__).resolve().parent


def parse_channels(gamedata):
    """channel(lower) -> {settings:[raw non-sounds lines], sound_paths:[sound paths]}.
    Reads sound_channels.ltx plus its ambient_channels includes."""
    env = Path(gamedata) / "configs/environment"
    files = [env / "sound_channels.ltx",
             env / "ambient_channels/blowout_channels.ltx",
             env / "ambient_channels/backgrounds.ltx"]
    ch, cur = {}, None
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = line
            code = line.split(";", 1)[0]
            m = re.match(r"\s*\[([^\]]+)\]", code)
            if m:
                cur = m.group(1).strip().lower()
                ch.setdefault(cur, {"settings": [], "sound_paths": []})
                continue
            if cur is None:
                continue
            if "sounds" in code and "=" in code:
                for token in code.split("=", 1)[1].split(","):
                    token = token.strip().replace("\\", "/")
                    if token and "no_sound" not in token:
                        ch[cur]["sound_paths"].append(token)
            elif code.strip():
                ch[cur]["settings"].append(raw.rstrip())
    return ch


def resolve(source_path, sounds_root):
    p = Path(sounds_root) / (source_path + ".ogg")
    return p if p.exists() else None


def hash_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def dedupe(files):
    """Keep the best-quality copy of each DISTINCT sound in a channel; collapse only
    true duplicates. Three-stage identity (architecture.md I3):
      1. md5   - byte-identical reships across packs collapse to one.
      2. fp    - Chromaprint proposes candidate same-sound groups (recall only; fp
                 cannot decide - its same/distinct similarity ranges overlap, a distinct
                 sound can score 1.0 and a re-encode 0.93).
      3. xcorr - PCM cross-correlation decides: two files merge only when their waveforms
                 correlate >= DEDUP_XCORR, under COMPLETE-LINKAGE (every pair in a merged
                 group confirms), so distinct variety is never merged and a similarity
                 chain cannot collapse transitively.
    Best-quality within a confirmed group is the highest bitrate; junk-bitrate files are
    dropped when the channel keeps better content."""
    # 1. exact byte dedup - each md5 group keeps its members, so the veto can later exclude the sound
    #    at every source path it collapsed from, not just the winner's.
    by_md5 = {}
    for f in files:
        f["hash"] = hash_file(f["abs"])
        by_md5.setdefault(f["hash"], []).append(f)
    md5_reps = []
    for group in by_md5.values():
        rep = max(group, key=lambda f: f["bitrate"])
        rep["_members"] = list(group)
        md5_reps.append(rep)
    # 1b. AUDIO-identity merge (n124): audio-identical files that differ ONLY in their comment blob have
    #     different md5, so stage 1 keeps them apart and the fuzzy stage can miss them. Group the md5-reps by
    #     _hash_audio (blob-agnostic, EXACT) to collapse them here. Collapsed paths ride _members -> dups, so
    #     the veto still strips the base copy at every path. Falls back to the whole-file hash on a bad ogg.
    by_audio = {}
    for rep in md5_reps:
        ah = _try_hash_audio(Path(rep["abs"])) or rep["hash"]
        by_audio.setdefault(ah, []).append(rep)
    reps = []
    for group in by_audio.values():
        rep = max(group, key=lambda f: f["bitrate"])
        rep["_members"] = [m for r in group for m in r.get("_members", [r])]
        reps.append(rep)
    if len(reps) <= 1:
        chosen = reps
    else:
        # 2. Chromaprint candidate clusters (duration-bucketed so only plausibly-same
        #    files ever get compared by the expensive step)
        fps = sp.pmap(lambda r: sp.fingerprint(r["abs"], FP_LEN), reps, sp.DEF_JOBS)
        durs = sp.pmap(lambda r: round(float((sp.probe(r["abs"]) or {}).get("duration") or 0)),
                       reps, sp.DEF_JOBS)
        for r, fp, du in zip(reps, fps, durs):
            r["_fp"] = fp
            r["_dur"] = du
        clusters = []
        for r in reps:
            for cl in clusters:
                h = cl[0]
                if (r["_fp"] and h["_fp"] and abs(r["_dur"] - h["_dur"]) <= 1
                        and sp.fp_similarity(r["_fp"], h["_fp"]) >= BASE_SIM):
                    cl.append(r)
                    break
            else:
                clusters.append([r])
        # 3. PCM cross-correlation confirm inside each candidate cluster (complete-linkage)
        chosen = []
        for cl in clusters:
            if len(cl) == 1:
                chosen.append(cl[0])
                continue
            decoded = sp.pmap(lambda r: sp.decode_pcm(r["abs"]), cl, sp.DEF_JOBS)
            pcm = {r["abs"]: d for r, d in zip(cl, decoded)}
            groups = []
            for r in cl:
                for g in groups:
                    if all(sp.pcm_correlation(pcm[r["abs"]], pcm[m["abs"]]) >= DEDUP_XCORR
                           for m in g):
                        g.append(r)
                        break
                else:
                    groups.append([r])
            for g in groups:
                winner = max(g, key=lambda f: f["bitrate"])
                winner["_members"] = [m for r in g for m in r.get("_members", [r])]
                chosen.append(winner)
    # record each kept copy's collapsed siblings (pool, source_path) - every other copy that merged into
    # it - so the veto excludes the sound at all source paths we drew it from, not only the winner's.
    for c in chosen:
        seen, dups = set(), []
        for m in c.get("_members", [c]):
            key = (m["pool"], m["source_path"])
            if key != (c["pool"], c["source_path"]) and key not in seen:
                seen.add(key)
                dups.append([m["pool"], m["source_path"]])
        c["dups"] = dups
        c.pop("_members", None)
    good = [c for c in chosen if c["bitrate"] >= LOWQ_BITRATE]
    return good if good else chosen


# --- routing / layer-map inputs: what the base install PLAYS -----------------
# We do NOT dedup against any target modpack: a sound is never dropped because the
# install already plays it. Doubling is handled at RUNTIME by the base-veto (as_director
# mutes the base's copy of a sound we ship, keyed off as_blockdata). _get_active_channels is
# kept only to resolve which channels a config plays, for the base dark-channel layer map
# and channel routing. Source-side waveform dedup (dedupe) is unaffected.
VAN_CFG = "D:/Games/GAMMA/Anomaly/tools/_unpacked"
GAMMA_WINNER = "D:/Games/GAMMA/GAMMA/mods/304- Dark Signal Weather and Ambiance Audio - Shrike/gamedata"
FP_LEN = 30
BASE_SIM = 0.88     # Chromaprint recall threshold: >= this makes a pair a same-sound CANDIDATE
DEDUP_XCORR = 0.90  # PCM cross-correlation DECIDER: >= this confirms a candidate is the same
                    # recording (a re-encode). Below it the pair is kept as distinct variety.
# NO loudness leveling. Each file's base_volume and min/max attenuation are the AUTHOR's, written verbatim by
# _normalize_blobs (or the category-median + base_volume 1.0 for a file that never carried a blob). The only
# loudness-domain drop is _cull_dead: after the stereo fold, a file whose audio is unmeasurable / true silence
# (peak -inf) is dropped as DEAD - never a quiet-but-real sound, which ships at its author's loudness (a faint
# feel is the director's placement, not removed content).
# astats reads the FLOAT-decoded samples, and a handful of vorbis decode outliers report an IMPOSSIBLE peak
# (measured +42..+82 dB on files that are actually 0 dBFS). Clamp anything above this ceiling so the dead-file
# measure is not fooled by a decode artefact (a real inter-sample overshoot stays under ~+6 dB).
PEAK_FLOAT_CEILING = 12.0
                    # Frozen as validated (MANGLE=0); see architecture.md I3.
# astats peak/rms per source path, memoized so a full `all` measures each file ONCE: cmd_deploy and
# cmd_provenance both cull-and-measure over the same tree in one process, and astats is deterministic.
_MEAS_CACHE = {}
# Long-file handling (n117): a sound whose ACTIVE (silence-removed) length exceeds the max emission tick
# outlives its slot and overlaps the next fire, so it is CULLED - EXCEPT dark_signal, which is SLICED into
# <=MAX_ACTIVE_S desilenced pieces (keeps the loved 4-min radio as clean pieces). Sliced/desilenced files
# re-encode -> lose the source X-Ray blob -> get the category-median blob at deploy (the one I5 exception).
MAX_ACTIVE_S     = 20.0
SILENCE_NOISE_DB = "-30dB"
SILENCE_MIN_S    = 0.5
SLICE_DIR        = HERE / "_sliced"


def _get_active_channels(gd):
    """channels PLAYED in a preset (static sound_channels + dynamic) on this install."""
    a = set()
    for _f, secs in parse_presets(gd).items():
        for _s, d in secs.items():
            a |= {c.lower() for c in d.get("base", [])} | {c.lower() for c in d.get("dynamic", [])}
    return a


def _fold_dups(home, dropped):
    """Fold a dropped byte-identical copy's origin - its own (pool, source_path) plus its own dups -
    into the kept home entry's `dups`, so the veto still excludes the sound at the dropped path."""
    have = {(pool, path) for pool, path in home.get("dups", [])}
    have.add((home["pool"], home["source_path"]))
    for pool, path in [[dropped["pool"], dropped["source_path"]]] + list(dropped.get("dups", [])):
        if (pool, path) not in have:
            have.add((pool, path))
            home.setdefault("dups", []).append([pool, path])


def _dedupe_across_channels(merged):
    """Drop byte-identical copies of a recording a source pack listed in more than one
    channel. md5-exact ONLY - a hash match is provably the same file, so no distinct
    sound can be lost (no fingerprint judgment, unlike _base_dedup). Keep one home per
    recording (first channel it appears in); never empty a channel."""
    seen = {}
    n_drop = 0
    for chan in merged:
        keep, dup = [], []
        for c in merged[chan]["chosen"]:
            h = hash_file(c["abs"])
            home = seen.get(h)
            if home is None:
                seen[h] = c
                keep.append(c)
            else:
                _fold_dups(home, c)                # the dropped copy's source path survives on the home
                dup.append(c)                      # byte-identical to a home in another channel
        if not keep and dup:                       # never-empty: rescue one as this channel's home
            rescued = dup.pop(0)
            seen[hash_file(rescued["abs"])] = rescued
            keep.append(rescued)
        n_drop += len(dup)
        merged[chan]["chosen"] = keep
    print(f"cross-channel dedup: dropped {n_drop} byte-identical copies (md5-exact, one home each)")


def _drop_silent(merged):
    """Drop dead/empty files ONLY - true peak level = -inf (no audio at all). Hard rule:
    never ship a silent sound (caught the shipped-dead ugrnd_lab/1-3). Uses the real peak
    (astats over the full-rate stream), NOT the 4kHz correlation PCM - so intentionally
    quiet or distant sounds (a faint owl at -17dB, a distant spook at -50dB) are KEPT;
    only a file with no audio at all is removed."""
    import subprocess, re
    def is_dead(a):
        r = subprocess.run([sp.tool("ffmpeg"), "-i", a, "-af", "astats=metadata=1:reset=0",
                            "-f", "null", "-"], capture_output=True, text=True)
        m = re.search(r"Peak level dB:\s*(\S+)", r.stderr)
        return (m is None) or (m.group(1) == "-inf")      # unmeasurable or true silence
    paths = list({c["abs"] for chan in merged for c in merged[chan]["chosen"]})
    dead = {a for a, d in zip(paths, sp.pmap(is_dead, paths, sp.DEF_JOBS)) if d}
    (HERE / "silence_dropped.json").write_text(
        json.dumps(sorted({hash_file(a) for a in dead})), encoding="utf-8")
    n = 0
    for chan in merged:
        before = len(merged[chan]["chosen"])
        merged[chan]["chosen"] = [c for c in merged[chan]["chosen"] if c["abs"] not in dead]
        n += before - len(merged[chan]["chosen"])
    print(f"silence gate: dropped {n} dead/empty files (true peak -inf, quiet sounds kept)")


def _cull_dead(effects):
    """Drop DEAD files only. After the stereo fold, measure each file's peak (astats Overall); a file whose
    audio is unmeasurable or true silence (peak/rms -inf) is dropped - the fold can cancel an anti-phase pair
    to silence, which _drop_silent (pre-fold) could not see. A quiet-but-real sound is KEPT and ships at its
    author's loudness; there is no leveling and no quiet-cull. Mutates effects."""
    import subprocess, re
    def measure(a):
        if a in _MEAS_CACHE:                                     # reuse across cmd_deploy + cmd_provenance
            return _MEAS_CACHE[a]
        r = subprocess.run([sp.tool("ffmpeg"), "-i", a, "-af", "astats=metadata=1:reset=0",
                            "-f", "null", "-"], capture_output=True, text=True)
        peaks = re.findall(r"Peak level dB:\s*(\S+)", r.stderr)   # per-channel first, Overall last
        rmss  = re.findall(r"RMS level dB:\s*(\S+)", r.stderr)
        res = None
        if peaks and rmss and peaks[-1] != "-inf" and rmss[-1] != "-inf":
            try:
                p, rms = float(peaks[-1]), float(rmss[-1])       # [-1] = the Overall block
                if p > PEAK_FLOAT_CEILING:                       # decode artefact -> treat as measurable (not dead)
                    p, rms = 0.0, -100.0
                res = (p, rms)
            except ValueError:
                res = None
        _MEAS_CACHE[a] = res
        return res
    paths = list({e["abs"] for cat in effects for e in effects[cat]})
    meas = dict(zip(paths, sp.pmap(measure, paths, sp.DEF_JOBS)))
    dropped = 0
    for cat in effects:
        kept = [e for e in effects[cat] if meas.get(e["abs"]) is not None]   # keep everything measurable
        dropped += len(effects[cat]) - len(kept)
        effects[cat] = kept
    print(f"dead-file cull: dropped {dropped} files (unmeasurable / true silence after fold)")


# Stereo -> mono masterization (n126). The engine 3D-positions MONO only; a 2-channel buffer force-2Ds to
# at-ear at full volume (SoundRender_Core.cpp:344,368,391) - the "one sound too loud" defect. Fold every
# stereo sound to mono at deploy so it positions. Deterministic (fixed libvorbis params), content-keyed
# cache under MONO_DIR so a re-build/re-add reuses it; delete MONO_DIR to force a re-fold after a param change.
MONO_DIR = HERE / "_mono"
_FOLD_CACHE = {}    # source abs -> (mono_path, method), reused across cmd_deploy + cmd_provenance in one `all`


def _masterize_channels(effects):
    """Fold every STEREO entry to mono (sp.to_mono: sum (L+R)/2, or drop a channel for an anti-phase pair
    where summing cancels), redirect its abs to a deterministic mono file, and mark it cut. Mono entries are
    left verbatim (source blob survives). Runs BEFORE _cull_dead so the dead-file check sees the MONO result,
    and before _deployed_name so identity is the mono audio hash. Mutates effects; safe to re-run (cached)."""
    stereo = [e for cat in effects for e in effects[cat] if e.get("channels", 0) >= 2]
    if not stereo:
        return
    MONO_DIR.mkdir(parents=True, exist_ok=True)

    def fold(e):
        if e["abs"] in _FOLD_CACHE:
            return _FOLD_CACHE[e["abs"]]
        method = sp.stereo_method(e["abs"])
        if method == "mono":                          # probe glitch on a known-stereo entry -> safe default
            method = "sum"
        out = MONO_DIR / f"{hash_file(e['abs'])[:12]}_{method}_q{sp.STEREO_ENCODE_Q}.ogg"
        res = (str(out), method) if (out.exists() or sp.fold_to_mono(e["abs"], out, method)) else None
        _FOLD_CACHE[e["abs"]] = res
        return res

    results = sp.pmap(fold, stereo, sp.DEF_JOBS)
    n = {"sum": 0, "drop": 0}
    fail = 0
    for e, res in zip(stereo, results):
        if res:
            try:                                       # capture the author blob BEFORE the fold redirect - the
                with open(e["abs"], "rb") as fh:       # mono re-encode strips it, so _normalize_blobs would
                    e["src_blob"] = _read_blob(fh.read(16384))   # otherwise fall back to the category median
            except OSError:
                e["src_blob"] = None
            e["abs"], method = res
            e["cut"] = True
            n[method] += 1
        else:
            fail += 1
    total = sum(len(v) for v in effects.values())
    print(f"stereo masterize: folded {n['sum']} sum + {n['drop']} drop -> mono ({len(stereo)} stereo of {total})")
    if fail:
        print(f"  ! WARNING: {fail} stereo files FAILED to fold - they ship STEREO (would 2D-blare); check ffmpeg")


def _dedupe_folded(effects):
    """Collapse entries that now share a deployed name (same mono audio) - two STEREO files that fold to
    identical mono, which the source dedup (running on the stereo audio) cannot see. Keep one entry per
    deployed name and fold the dropped entries' source_path + dups into the SURVIVOR's dups, so the veto still
    strips the base copy at EVERY path. Runs after _masterize_channels, in BOTH deploy and provenance, so the
    two agree. Mono audio-identical duplicates are already merged upstream by dedupe stage 1b; this catches
    only what the fold newly makes identical. Mutates effects."""
    collapsed = 0
    for cat in effects:
        seen, kept = {}, []
        for e in effects[cat]:
            name = _deployed_name(e)
            surv = seen.get(name)
            if surv is not None:
                surv["dups"] = surv.get("dups", []) + [[e["pool"], e["source_path"]]] + e.get("dups", [])
                collapsed += 1
            else:
                seen[name] = e
                kept.append(e)
        effects[cat] = kept
    if collapsed:
        print(f"folded-dup collapse: merged {collapsed} same-mono duplicates (survivor keeps every veto path)")


def _get_active_seconds(abs_path, duration):
    """Non-silent seconds = duration minus the total silence ffmpeg silencedetect reports."""
    import subprocess
    r = subprocess.run([sp.tool("ffmpeg"), "-i", abs_path, "-af",
                        f"silencedetect=noise={SILENCE_NOISE_DB}:d={SILENCE_MIN_S}", "-f", "null", "-"],
                       capture_output=True, text=True)
    silence = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", r.stderr))
    return max(0.0, duration - silence)


def _slice_file(abs_path, out_dir, base):
    """Strip silence, then segment into <=MAX_ACTIVE_S pieces (re-encoded vorbis). Returns the piece paths."""
    import subprocess
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / f"{base}_%03d.ogg")
    subprocess.run([sp.tool("ffmpeg"), "-y", "-i", abs_path, "-af",
                    f"silenceremove=stop_periods=-1:stop_duration={SILENCE_MIN_S}:stop_threshold={SILENCE_NOISE_DB}",
                    "-f", "segment", "-segment_time", str(int(MAX_ACTIVE_S)),
                    "-c:a", "libvorbis", "-ar", "44100", pattern],
                   capture_output=True, text=True)
    return sorted(out_dir.glob(f"{base}_*.ogg"))


def _cull_long_files(merged):
    """Cull files whose ACTIVE length > MAX_ACTIVE_S; dark_signal is SLICED into desilenced pieces instead.
    Only RAW-duration-over-cap files are silencedetect-probed (active <= raw), so the pass runs on the few
    long files, not the whole corpus. Books culled + sliced-original hashes so the ledger keeps UNUSED-DARK 0."""
    import shutil
    if SLICE_DIR.exists():
        shutil.rmtree(SLICE_DIR)
    culled, sliced_orig, sliced_to = [], [], 0
    for cat in merged:
        new_chosen = []
        for c in merged[cat]["chosen"]:
            if float(c.get("dur") or 0.0) <= MAX_ACTIVE_S:      # raw already short -> active shorter, keep
                new_chosen.append(c)
                continue
            active = _get_active_seconds(c["abs"], float(c.get("dur") or 0.0))
            if active <= MAX_ACTIVE_S:
                new_chosen.append(c)
            elif cat == "dark_signal":
                sliced_orig.append(c["hash"])
                for p in _slice_file(Path(c["abs"]), SLICE_DIR / cat, Path(c["source_path"]).name):
                    sliced_to += 1
                    piece = dict(c)
                    piece.update(abs=str(p), source_path=Path(c["source_path"]).as_posix() + "#" + p.stem,
                                 hash=hash_file(p), cut=True)
                    new_chosen.append(piece)
            else:
                culled.append(c["hash"])
        merged[cat]["chosen"] = new_chosen
    (HERE / "longfile_culled.json").write_text(json.dumps(sorted(set(culled))), encoding="utf-8")
    (HERE / "sliced_dropped.json").write_text(json.dumps(sorted(set(sliced_orig))), encoding="utf-8")
    print(f"long-file pass: culled {len(culled)} (active > {int(MAX_ACTIVE_S)}s); "
          f"sliced {len(sliced_orig)} dark_signal -> {sliced_to} pieces")


def _scan_source(name, gd, pool, audit):
    """Walk ONE pack's sound tree, route each ogg to a category by its FOLDER PATH (route), gate on 44100,
    and pool it (updating the folder audit). Returns (off_rate, out_of_scope) counts. This is the single
    capture rule, shared by cmd_plan (the full scan over MODS) and cmd_add (one added source), so the full
    and additive builds route and gate identically - no second definition that could drift."""
    offrate = dropped = 0
    sroot = Path(gd) / "sounds"
    if not sroot.is_dir():
        print(f"  ! WARNING: source '{name}' has no sounds/ at {gd} - SKIPPED, its content is NOT in the build")
        return offrate, dropped
    for f in sorted(sroot.rglob("*.ogg")):
        cat = route(f.as_posix())
        if not cat:
            dropped += 1
            continue
        info = sp.probe(str(f)) or {}
        if info.get("sample_rate") != 44100:                   # X-Ray fitness: 44100 only
            offrate += 1
            continue
        rel = f.as_posix().split("/sounds/", 1)[-1]
        pool[cat].append({"abs": str(f), "source_path": rel[:-4], "pool": name,
                          "bitrate": info.get("bit_rate", 0), "channels": info.get("channels", 0),
                          "dur": info.get("duration") or 0.0})
        audit[cat][name + ":" + str(Path(rel).parent)] += 1
    return offrate, dropped


def cmd_plan(_):
    # STRUCTURAL per-file capture (n117): walk every pack's sound tree, route each file to a category by
    # its FOLDER PATH (route), gate on 44100, pool by category. No channel parsing - the packs ship far
    # more dark content than they wire, so the folder trees are the source of truth. Unmatched files are
    # dropped (dark scope, I9); the folder audit proves no generic folder leaked in.
    pool = collections.defaultdict(list)                        # category -> [file dicts]
    audit = collections.defaultdict(collections.Counter)       # category -> {source_folder: count}
    offrate = dropped_scope = 0
    for name, gd in MODS:
        o, d = _scan_source(name, gd, pool, audit)
        offrate += o
        dropped_scope += d

    # dedup per category (source-side waveform), then silence + cross-category dedup
    merged = {}
    tot_in = tot_kept = 0
    kept_hashes = set()
    for cat in CATEGORIES:
        files = pool.get(cat, [])
        tot_in += len(files)
        chosen = dedupe(files) if files else []
        kept_hashes |= {c["hash"] for c in chosen}
        tot_kept += len(chosen)
        merged[cat] = {
            "chosen": [{"abs": c["abs"], "source_path": c["source_path"], "pool": c["pool"], "hash": c["hash"],
                        "bitrate": c["bitrate"], "channels": c["channels"], "dur": c.get("dur", 0.0),
                        "dups": c.get("dups", [])}
                       for c in chosen],
        }
    # Intra-corpus re-encodes the PCM dedup dropped: their hashes, so the ledger books them as
    # captured-then-deduped, not a coverage miss (md5-losers share the winner's hash, already in kept).
    pool_hashes = {f["hash"] for fs in pool.values() for f in fs if "hash" in f}
    (HERE / "intra_dups.json").write_text(json.dumps(sorted(pool_hashes - kept_hashes)), encoding="utf-8")
    # No target-modpack dedup. Doubling with the base is handled at config load by the static DLTX veto.
    _drop_silent(merged)
    _dedupe_across_channels(merged)
    _cull_long_files(merged)                    # cull active > 20s; slice dark_signal into desilenced pieces
    (HERE / "merged_channels.json").write_text(json.dumps(merged, indent=1), encoding="utf-8")

    # folder audit: per category, the source folders it pulled, so a wrong/generic folder shows.
    audit_lines = ["category\tsounds\tsource_folders(count)"]
    for cat in CATEGORIES:
        srcs = "; ".join(f"{d}({k})" for d, k in sorted(audit[cat].items()))
        audit_lines.append(f"{cat}\t{len(merged[cat]['chosen'])}\t{srcs}")
    (HERE / "folder_audit.tsv").write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

    # report
    print(f"mods: {[m[0] for m in MODS]}")
    net = sum(len(v["chosen"]) for v in merged.values())
    print(f"categories: {len(merged)}   pooled {tot_in} -> deduped {tot_kept} -> shipped {net}   "
          f"(dropped out-of-scope {dropped_scope}; off-44100 {offrate})")
    for cat in CATEGORIES:
        print(f"  {cat:24s} {len(merged[cat]['chosen']):4d}")


def parse_presets(gamedata):
    """{filename: {section: {base:[...], lines:[effect/period raw], dynamic:[layers]}}}"""
    d = Path(gamedata) / "configs/environment/ambients/presets"
    out = {}
    if not d.exists():
        return out
    for f in sorted(d.glob("*.ltx")):
        secs, cur = {}, None
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            code = line.split(";", 1)[0]
            m = re.match(r"\s*\[([^\]]+)\]", code)
            if m:
                cur = m.group(1).strip().lower()
                secs[cur] = {"base": [], "lines": [], "dynamic": []}
                continue
            if cur is None:
                continue
            if "sound_channels_dynamic" in code and "=" in code:
                secs[cur]["dynamic"] = [t.strip().lower() for t in code.split("=", 1)[1].split(",") if t.strip()]
            elif re.search(r"sound_channels\s*=", code):
                secs[cur]["base"] = [t.strip() for t in code.split("=", 1)[1].split(",") if t.strip()]
            elif code.strip() and "=" in code:
                secs[cur]["lines"].append(line.rstrip())
        out[f.name] = secs
    return out


MOD = HERE.parent                      # AlifeSpooks repo root
GDATA = MOD / "gamedata"
ENV = GDATA / "configs/environment"
SND = GDATA / "sounds/zs"              # zs\<layer>\<channel>\N.ogg (layer = our category dir)
HDR = "; GENERATED"


def _clean(d):
    if d.exists():
        import shutil as sh
        sh.rmtree(d)


# ----------------------------------------------------------------------------
# The shipped model: one-shot spook channels the standalone director (as_director) plays. Every dark
# channel with content deploys as our own as_<ch> under its category layer (zs\<layer>\<channel>),
# grouped into 11 LAYERS (layer_of) for the MCM volume sliders. There is no loop layer and no
# loop/effect split - a long horror drone or psy bed plays as a one-shot on a long tuned period
# (see _tune_period). classify measures each file (duration/brightness/tone) for period tuning.
# ----------------------------------------------------------------------------


def _iterate_chosen(mc):
    """Every chosen sound across all channels, in the canonical order
    (sorted channel name, then the channel's chosen order). This order defines
    classification.json and, downstream, the deployed N numbering."""
    for chan in sorted(mc):
        for c in mc[chan]["chosen"]:
            yield chan, c


# --- classify (measured features per sound) ----------------------------------

def _classify_one(chan, c):
    abs_ = c["abs"]
    info = sp.probe(abs_) or {}
    dur = round(float(info.get("duration") or 0.0), 1)
    # one ffmpeg pass: spectral centroid + flatness (stdout via ametadata print),
    # crest factor (stderr astats summary).
    r = sp.run([sp.tool("ffmpeg"), "-v", "info", "-i", abs_, "-af",
                "aspectralstats=measure=centroid+flatness,ametadata=mode=print:file=-,"
                "astats=metadata=1:reset=0", "-f", "null", "-"])
    cens, flats = [], []
    for ln in r.stdout.splitlines():
        if "aspectralstats.1.centroid=" in ln:
            cens.append(float(ln.rsplit("=", 1)[1]))
        elif "aspectralstats.1.flatness=" in ln:
            flats.append(float(ln.rsplit("=", 1)[1]))
    crest = 0.0
    for ln in r.stderr.splitlines():
        if "Crest factor:" in ln:
            try:
                crest = float(ln.rsplit(":", 1)[1])
            except ValueError:
                pass
            break
    cen = int(round(sum(cens) / len(cens))) if cens else 0
    flat = round(sum(flats) / len(flats), 3) if flats else 0.0
    bright = "dark" if cen < 2000 else ("mid" if cen < 4000 else "bright")
    tone = "tonal" if flat < 0.15 else ("mixed" if flat < 0.40 else "noisy")
    return {"ch": chan, "source_path": c["source_path"], "dur": dur, "cen": cen, "flat": flat,
            "crest": round(crest, 1), "bright": bright, "tone": tone}


def cmd_classify(a):
    mc = json.loads((HERE / "merged_channels.json").read_text())
    items = list(_iterate_chosen(mc))
    out = sp.pmap(lambda item: _classify_one(*item), items, sp.DEF_JOBS)
    dst = Path(a.out) if a.out else (HERE / "classification.json")
    dst.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"classified {len(out)} sounds (all one-shot effects) -> {dst.name}")


# --- loudness (per-group median leveling, outliers only) ---------------------

def _measure_lufs(abs_):
    r = sp.run([sp.tool("ffmpeg"), "-i", abs_, "-af", "ebur128", "-f", "null", "-"])
    val = None
    for ln in r.stderr.splitlines():
        m = re.search(r"\bI:\s*(-?[0-9.]+)\s*LUFS", ln)
        if m:
            val = float(m.group(1))
    return val


def _median(xs):
    s = sorted(xs); n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def cmd_loudness(a):
    mc = json.loads((HERE / "merged_channels.json").read_text())
    items = list(_iterate_chosen(mc))
    lufs = sp.pmap(lambda item: (item[0], item[1]["source_path"], _measure_lufs(item[1]["abs"])), items, sp.DEF_JOBS)
    by_ch = collections.defaultdict(list)
    for ch, source_path, L in lufs:
        if L is not None:
            by_ch[ch].append((source_path, L))
    outliers = []
    for ch, rows in by_ch.items():
        vals = sorted(L for _, L in rows)
        med = _median(vals)
        q1 = _median(vals[:len(vals) // 2])
        q3 = _median(vals[(len(vals) + 1) // 2:])
        band = max(6.0, 1.5 * (q3 - q1))
        for source_path, L in rows:
            if abs(L - med) > band:
                outliers.append({"ch": ch, "source_path": source_path, "gain_db": round(med - L, 1)})
    dst = Path(a.out) if a.out else (HERE / "loudness_outliers.json")
    dst.write_text(json.dumps(outliers, indent=1), encoding="utf-8")
    print(f"loudness: {len(outliers)} outliers ({100*len(outliers)//max(1,len(lufs))}%) to gain -> {dst.name}")


# --- deploy (deterministic: reproduces the N numbering from the JSONs) --------

def _build_layers(mc, cls, ch_to_group):
    """Group every chosen sound into its director CATEGORY (the shipped directory), deterministically.
    classification.json is produced by classifying _iterate_chosen(mc) in order, so cls[i] IS the
    classification of the i-th chosen entry - align POSITIONALLY, not by (ch,source_path). Two chosen
    entries can share a source path (distinct sounds a pack shipped under one filename that PCM proved
    different); a (ch,source_path) lookup collapsed them. Positional alignment ships each exactly once."""
    chosen_seq = list(_iterate_chosen(mc))
    assert len(cls) == len(chosen_seq), (
        f"classification.json ({len(cls)}) out of sync with merged_channels.json "
        f"({len(chosen_seq)}); rerun classify after plan")
    effects = {cat: [] for cat in set(ch_to_group.values())}
    for idx, (r, (ch, c)) in enumerate(zip(cls, chosen_seq)):
        assert r["ch"] == ch and r["source_path"] == c["source_path"], (
            f"classification out of sync with merged_channels at row {idx}; rerun classify")
        if ch in ch_to_group:
            effects[ch_to_group[ch]].append(
                {"ch": ch, "source_path": c["source_path"], "abs": c["abs"], "pool": c["pool"],
                 "dups": c.get("dups", []), "dur": r["dur"], "crest": r.get("crest", 0),
                 "idx": idx, "channels": c.get("channels", 0)})
    return effects


def _emit_audio(entry, dst):
    # Copy every sound VERBATIM (byte-for-byte): no re-encode, no sample gain. The source blob is
    # copied along with it here; _normalize_blobs (called next in cmd_deploy) then REWRITES the blob
    # in place with the AUTHOR's own min/max and base_volume, verbatim, as a lossless header-page
    # rewrite, the audio pages staying byte-identical. So the samples are never touched and no
    # leveling of any kind is applied.
    dst.parent.mkdir(parents=True, exist_ok=True)
    import shutil as sh
    sh.copy2(entry["abs"], dst)


def _stamp_buckets(effects, snd):
    """Stamp e['bucket'] = the dread bucket a sound already sits in (its subdir under zs/<cat>/), else 'all'.
    A file directly under zs/<cat>/ (the pre-bucket flat layout) reads as 'all', so the first bucketed build
    migrates it. rebuild wipes zs/ before this runs, so the scan is empty and everything is 'all'; add keeps
    the tree, so curated buckets survive. No side file - the tree IS the record."""
    here = {}
    if snd.exists():
        base = str(snd).replace("\\", "/").rstrip("/")
        for ogg in snd.rglob("*.ogg"):
            parts = str(ogg).replace("\\", "/")[len(base) + 1:].split("/")
            if len(parts) < 2:
                continue
            bucket = parts[1] if len(parts) > 2 else "all"
            here.setdefault(parts[0], {})[parts[-1][:-4]] = bucket
    for cat in effects:
        m = here.get(cat, {})
        for e in effects[cat]:
            e["bucket"] = m.get(_deployed_name(e), "all")


def _remove_stale(snd, effects):
    """The no-wipe path leaves the tree in place, so drop any deployed ogg no longer in the corpus."""
    keep = set()
    for cat in effects:
        for e in effects[cat]:
            keep.add((cat, _deployed_name(e)))
    if not snd.exists():
        return
    base = str(snd).replace("\\", "/").rstrip("/")
    for ogg in snd.rglob("*.ogg"):
        parts = str(ogg).replace("\\", "/")[len(base) + 1:].split("/")
        if (parts[0], parts[-1][:-4]) not in keep:
            ogg.unlink()


# --- n108: X-Ray ogg comment blob (per-file min/max distance + base_volume) ------------
# The engine reads the FIRST vorbis comment of an ogg as a binary struct (version 0x0003:
# u32 ver, f32 min, f32 max, f32 base_volume, u32 game_type, f32 max_ai) and applies
# base_volume plus the min/max attenuation at play (SoundRender_Source_loader.cpp:108-152,
# SoundRender_Emitter_FSM.cpp:133,361). A missing/text-tagged comment falls back to 1/300 +
# base_volume 1.0. ffmpeg CANNOT write it (it emits text tags), so we rewrite the comment
# header page directly - lossless: only page 1 changes, the audio pages are byte-identical.

def _compute_ogg_crc(data):
    crc = 0
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04c11db7) & 0xffffffff if (crc & 0x80000000) else (crc << 1) & 0xffffffff
    return crc


def _read_ogg_pages(d):
    off, out = 0, []
    while off < len(d) and d[off:off + 4] == b"OggS":
        nseg = d[off + 26]
        segs = d[off + 27:off + 27 + nseg]
        dlen = sum(segs)
        out.append((off, bytes(segs), d[off + 27 + nseg:off + 27 + nseg + dlen]))
        off += 27 + nseg + dlen
    return out, off


def _read_ogg_packets(segs, body):
    pkts, cur, start = [], 0, 0
    for s in segs:
        cur += s
        if s < 255:
            pkts.append(body[start:start + cur]); start += cur; cur = 0
    return pkts


def _read_blob(d):
    """comment[0] as (min, max, base_volume) when it is a valid X-Ray blob, else None."""
    i = d.find(b"\x03vorbis")
    if i < 0:
        return None
    p = i + 7
    (vl,) = struct.unpack("<I", d[p:p + 4]); p += 4 + vl
    (n,) = struct.unpack("<I", d[p:p + 4]); p += 4
    if n == 0:
        return None
    (cl,) = struct.unpack("<I", d[p:p + 4]); p += 4
    c0 = d[p:p + cl]
    if len(c0) < 4:
        return None
    (v,) = struct.unpack("<I", c0[:4])
    if v == 1 and len(c0) >= 16:
        mn, mx = struct.unpack("<ff", c0[4:12]); return (mn, mx, 1.0)
    if v in (2, 3) and len(c0) >= 20:
        mn, mx, bv = struct.unpack("<fff", c0[4:16]); return (mn, mx, bv)
    return None


def _build_ogg_page(htype, granule, serial, seq, packets):
    segtab, body = [], b""
    for packet in packets:
        seg_len = len(packet)
        while seg_len >= 255:
            segtab.append(255); seg_len -= 255
        segtab.append(seg_len); body += packet
    if len(segtab) > 255:
        return None
    page = (b"OggS" + bytes([0, htype]) + struct.pack("<q", granule) +
            struct.pack("<I", serial) + struct.pack("<I", seq) +
            struct.pack("<I", 0) + bytes([len(segtab)]) + bytes(segtab) + body)
    return page[:22] + struct.pack("<I", _compute_ogg_crc(page)) + page[26:]


def _write_blob(path, mn, mx, bv):
    """Write a 0x0003 X-Ray blob as comment[0], losslessly. Only the standard
    [ID | comment+setup | audio...] layout is handled; anything else is left unchanged
    (returns False). Audio pages are byte-identical after the write."""
    d = path.read_bytes()
    pg, end = _read_ogg_pages(d)
    if end != len(d) or len(pg) < 3:
        return False
    pkts = _read_ogg_packets(pg[1][1], pg[1][2])
    if len(pkts) != 2 or not pkts[0].startswith(b"\x03vorbis") or not pkts[1].startswith(b"\x05vorbis"):
        return False
    comment_pkt, setup_pkt = pkts
    p = 7
    (vl,) = struct.unpack("<I", comment_pkt[p:p + 4]); p += 4
    vendor = comment_pkt[p:p + vl]
    blob = struct.pack("<I", 3) + struct.pack("<fff", mn, mx, bv) + struct.pack("<I", 0) + struct.pack("<f", mx)
    new_comment = (b"\x03vorbis" + struct.pack("<I", len(vendor)) + vendor +
                   struct.pack("<I", 1) + struct.pack("<I", len(blob)) + blob + b"\x01")
    o = pg[1][0]
    htype = d[o + 5]
    gran = struct.unpack("<q", d[o + 6:o + 14])[0]
    serial = struct.unpack("<I", d[o + 14:o + 18])[0]
    seq = struct.unpack("<I", d[o + 18:o + 22])[0]
    new_p1 = _build_ogg_page(htype, gran, serial, seq, [new_comment, setup_pkt])
    if new_p1 is None:
        return False
    path.write_bytes(d[:pg[1][0]] + new_p1 + d[pg[2][0]:])
    return True


_AUDIO_HASH_CACHE = {}   # str(path) -> audio-page md5; safe within a run (the blob rewrite never touches audio pages)


def _hash_audio(path):
    """md5 of the audio pages (everything after the ID + comment/setup header pages), so a
    comment-blob rewrite still verifies as the same audio as its verbatim source. Memoized per path -
    _deployed_name/dedup call it repeatedly and a path's audio is fixed within a run."""
    key = str(path)
    cached = _AUDIO_HASH_CACHE.get(key)
    if cached is not None:
        return cached
    pg, _ = _read_ogg_pages(path.read_bytes())
    h = hashlib.md5(b"".join(p[2] for p in pg[2:])).hexdigest()
    _AUDIO_HASH_CACHE[key] = h
    return h


def _try_hash_audio(path):
    """_hash_audio, or None on a malformed/unreadable ogg (never abort the scan for one bad file)."""
    try:
        return _hash_audio(path)
    except Exception:
        return None


def _slug(name):
    """Filesystem-safe lowercase slug of a source filename: letters, digits, underscore only."""
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "sound"


def _deployed_name(entry):
    """The n124 deployed name (no extension): <source-name slug>_<audio hash>. Deterministic - depends
    only on the entry's own filename and audio, so every stage recomputes the same name with no shared
    counter, and the blob-agnostic audio hash means writing the ogg blob never changes it. The hash
    disambiguates two distinct sounds a pack shipped under one filename; identical audio collapses to one
    file. Replaces the positional N that re-indexed the whole tree whenever content was added or removed."""
    base = _slug(Path(entry["source_path"]).name)
    h = (_try_hash_audio(Path(entry["abs"])) or hash_file(entry["abs"]))[:10]
    return f"{base}_{h}"


def _read_channel_sounds(sc_path):
    """channel(lower) -> list of raw `sounds` entries (trimmed, ORIGINAL case/backslashes) in a
    sound_channels.ltx. The raw string is kept verbatim so a DLTX `<sounds = X` removal matches the base
    list item exactly (the engine removes by exact string, Xr_ini.cpp:1259-1263)."""
    ch, cur = {}, None
    for line in Path(sc_path).read_text(encoding="utf-8", errors="replace").splitlines():
        code = line.split(";", 1)[0]
        m = re.match(r"\s*\[([^\]]+)\]", code)
        if m:
            cur = m.group(1).strip().lower()
            ch.setdefault(cur, [])
        elif cur is not None and re.match(r"\s*sounds\s*=", code):
            for token in code.split("=", 1)[1].split(","):
                token = token.strip()
                if token and "no_sound" not in token.lower():
                    ch[cur].append(token)
    return ch


def _source_channels_raw(gd):
    """channel(lower) -> list of RAW `sounds` entries across a source's three ambient channel files
    (sound_channels.ltx, backgrounds.ltx, blowout_channels.ltx). Raw (original case + backslashes) so a
    DLTX `<sounds = X` removal matches the base list item exactly - and because this is
    the source pack's OWN config, that string is byte-identical to what a user running the pack loads, so
    the exact-string removal (Xr_ini.cpp:1257-1266) is guaranteed to hit."""
    env = Path(gd) / "configs/environment"
    files = [env / "sound_channels.ltx",
             env / "ambient_channels/backgrounds.ltx",
             env / "ambient_channels/blowout_channels.ltx"]
    out = {}
    for f in files:
        if not f.is_file():
            continue
        for chan, raws in _read_channel_sounds(f).items():
            out.setdefault(chan, []).extend(raws)
    return out


def _build_veto_overlay(effects):
    """Static DLTX overlay that removes our own sounds from the base ambient channels so the base never
    doubles the director. Derived from the pipeline's OWN record - the chosen corpus - not the build
    machine's installed packs. Every shipped sound was captured from a registry source (sources.py) at a
    known path; a source wires that path to a channel only in its own config, the same file a user running
    that pack loads. So for each shipped sound we read its origin pack's channels and emit `![channel]` +
    `<sounds = <verbatim path>` wherever the pack lists it - complete by construction and independent of any
    install: a pack we never sourced holds none of our audio, so nothing of ours can double there.

    Dedup collapsed byte-identical and re-encoded copies across packs; each shipped sound carries the
    (pool, source_path) of every copy that merged into it (`dups`), so the removal covers EVERY source path
    we drew the sound from, not only the winner's. Every removed-from channel also gets
    `>sounds = ambient\\no_sound` - a System A bed CTDs on an empty `sounds` (Environment_misc.cpp:105-108)
    and no_sound is silent, so a full removal never empties a bed and a partial one is only marginally
    diluted. Returns (overlay_text, report)."""
    # every (pack, source-path) we ship from: the winner plus its collapsed dedup siblings. Lower-cased for
    # the match - a pack's config path case can differ from its filesystem case.
    ship = collections.defaultdict(set)
    ship_entries = 0
    for entries in effects.values():
        for e in entries:
            ship[e["pool"]].add(e["source_path"].lower())
            ship_entries += 1
            for pool, path in e.get("dups", ()):
                ship[pool].add(path.lower())

    removals = {}                          # channel(lower) -> set of raw verbatim strings
    contributing = collections.Counter()
    wired = set()                          # (pack, lower path) actually found wired in a source channel
    for name, gd in MODS:
        want = ship.get(name)
        if not want:                       # shipped nothing from this pack (or it is channel-less, e.g. a build)
            continue
        for chan, raws in _source_channels_raw(gd).items():
            for raw in raws:
                norm = raw.replace("\\", "/").lower()
                if norm in want:
                    removals.setdefault(chan, set()).add(raw)
                    contributing[name] += 1
                    wired.add((name, norm))

    unique_paths = sum(len(v) for v in ship.values())
    out = ["; GENERATED by tools/build.py - do not edit. Static DLTX veto: removes AlifeSpooks' own",
           "; sounds from the base ambient channels so the base never doubles the director's copy.",
           "; Derived from the source REGISTRY (sources.py), not any install: every shipped sound is",
           "; removed at the path(s) we captured it from, in the channel(s) its source pack defines,",
           "; so coverage is complete by construction and independent of the player's modlist.",
           ";",
           "; Sources vetoed (pack (channel entries removed)):"]
    for name in sorted(contributing):
        out.append(";   %s (%d)" % (name, contributing[name]))
    out.append(";")
    out.append("; Coverage: %d shipped source-paths; %d wired in a source channel and removed here;"
               % (unique_paths, len(wired)))
    out.append(";   %d captured from a folder tree no source channel wires (base plays them via no channel)."
               % (unique_paths - len(wired)))
    out.append("")
    for chan in sorted(removals):
        out.append("![%s]" % chan)
        for raw in sorted(removals[chan]):
            out.append("<sounds = %s" % raw)
        out.append(">sounds = ambient\\no_sound")
        out.append("")
    report = {"ship_entries": ship_entries, "unique_paths": unique_paths, "wired_removed": len(wired),
              "folder_only": unique_paths - len(wired), "channels": len(removals),
              "removals": sum(len(v) for v in removals.values())}
    return "\n".join(out), report


# No placement-distance clamp. _normalize_blobs ships each file's AUTHORED min/max attenuation verbatim;
# placement is the sound's own source-channel spawn band through the vanilla formula (as_director emit),
# never derived from this pair. The author's range is trusted (only guard is max > min for the engine
# divide). The distance-baked / constant-volume sounds authored at 300-10000m are meant to play at a steady
# level and stay untouched.


# min_distance floor (2026-08-21, user-approved). The OpenAL layer attenuates every 3D voice by an inverse
# curve keyed on the blob min (AL_REFERENCE_DISTANCE, TargetA.cpp:166; model never disabled). 61% of the
# corpus carries the UNSET default min 1-2 ("whisper"), which costs -25..-33 dB at the felt placement
# distances and silenced the director. The floor raises each file's written min to (ratio x its felt-far
# distance = band_max/2). Authored mins ABOVE the floor are kept verbatim; the floor never lowers anyone.
# FLOOR_MAX_FRAC caps the floor below the blob max so a real fade band survives.
#
# The ratio is not flat. PRINCIPLE (measured, mild-moderate, automated): placement loudness follows crest,
# INVERTED. A sustained low-crest tone carries in air -> higher ratio -> stays present at distance; a sharp
# high-crest transient is a near-field detail -> lower ratio -> stays intimate. Crest is measured per file
# (classification.json). Verified across the corpus: transients (drip 24dB, rats 18, foliage 17) are the
# sharp near-field sounds; the sustained dread (drone/scream/mutant/spook ~6-7dB) carries. The span 0.40-0.60
# centers on the old flat 0.5 (~3 dB spread at the far edge), so nothing shifts dramatically.
RATIO_HI       = 0.60   # sustained (low crest): carries, present at distance
RATIO_LO       = 0.40   # transient (high crest): near-field, intimate
CREST_LO       = 6.0    # dB, corpus floor (sustained) -> RATIO_HI
CREST_HI       = 24.0   # dB, corpus ceiling (sharpest transient) -> RATIO_LO
FLOOR_MAX_FRAC = 0.8


def _crest_ratio(crest):
    """Crest (dB) -> min/felt-far ratio, INVERTED: high crest (transient) -> RATIO_LO, low crest (sustained)
    -> RATIO_HI. Clamped to the corpus crest span."""
    t = (crest - CREST_LO) / (CREST_HI - CREST_LO)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return RATIO_HI - (RATIO_HI - RATIO_LO) * t


def _normalize_blobs(effects, snd, bands):
    """Write every kept file's ogg blob from the author's values: min/max attenuation range and base_volume
    unchanged EXCEPT the min_distance floor (crest-inverted ratio x the sound's felt-far placement, above) - the one
    uniform, declared transform, correcting the field the pack tooling never authored. NO leveling
    (base_volume is the author's number, or 1.0 when the source carried none or <=0). A blob-less /
    re-encoded file (folded stereo, sliced dark_signal) has no authored blob, so it inherits its category's
    median min/max and base_volume 1.0, then the same floor. Safety: max nudged above min so the engine's
    (max-min) divide (Emitter_FSM.cpp:361) can't be zero and the loader assert (max>=0.1,
    Source_loader.cpp:152) holds. Lossless bitstream rewrite, no re-encode. `bands` = id(entry) ->
    (ch_min, ch_max, indoor), the resolved spawn band per sound."""
    wrote = skipped = floored = 0
    for cat in sorted(effects):
        names = [_deployed_name(e) for e in effects[cat]]
        blobs = [_read_blob((snd / cat / e["bucket"] / f"{n}.ogg").read_bytes()) for e, n in zip(effects[cat], names)]
        carried = [b for b in blobs if b]
        cmin = _median(sorted(c[0] for c in carried)) if carried else 1.0
        cmax = _median(sorted(c[1] for c in carried)) if carried else 100.0
        if cmax <= cmin:
            cmax = cmin + 1.0
        for e, n, b in zip(effects[cat], names, blobs):
            b = b or e.get("src_blob")   # a folded-stereo file lost its deployed blob; recover the author's original
            if b:
                mn, mx, bv = b[0], b[1], (b[2] if b[2] > 0 else 1.0)   # author's range + loudness, verbatim
            else:
                mn, mx, bv = cmin, cmax, 1.0                          # never had a blob -> category median + 1.0
            if mn < 0.0:
                mn = 0.0
            band = bands.get(id(e))
            if band:
                floor = _crest_ratio(e.get("crest", 0)) * (band[1] / 2.0)   # crest-inverted ratio x felt-far
                if floor > mx * FLOOR_MAX_FRAC:
                    floor = mx * FLOOR_MAX_FRAC
                if mn < floor:
                    mn = floor
                    floored += 1
            if mx < mn + 0.1:                                          # engine (max-min) divide / loader safety
                mx = mn + 0.1
            if _write_blob(snd / cat / e["bucket"] / f"{n}.ogg", mn, mx, bv):
                wrote += 1
            else:
                skipped += 1
    print(f"normalize: wrote author blob + crest-inverted min floor (ratio {RATIO_LO}-{RATIO_HI}) for {wrote} "
          f"files; floored {floored}; skipped {skipped} (non-standard ogg layout)")


# Each effect channel keeps its VERBATIM source settings - no median. Channels are grouped
# by (mood, exact-settings-tuple): one deployed channel as_eff_<mood>_<n> per distinct tuple,
# so a source channel's period/distance/indoor/height survive exactly (provenance-faithful).
# The mood is only a tag for the MCM knobs; as_director reads it off the <mood> in the name.
def _parse_channel_settings(lines):
    d = {}
    for ln in lines or []:
        m = re.match(r"\s*(\w+)\s*=\s*([\d.]+|true|false)", ln)
        if m:
            d[m.group(1)] = m.group(2)

    def num(x, dflt):
        try:
            return int(float(x))
        except (TypeError, ValueError):
            return dflt
    return {"min": num(d.get("min_distance"), 45), "max": num(d.get("max_distance"), 80),
            "p": tuple(num(d.get(f"period{i}"), 0) for i in range(4)),
            "indoor": d.get("indoor") == "true", "height": num(d.get("height"), 0)}


# The category table (CATEGORIES, top of file) is the single source of truth. merged_channels.json is
# keyed by category directly (structural per-file capture), so the deploy groups by category identity -
# no channel->category mapping. The shipped directory is zs\<category>.


def build_effect_group_map():
    """category -> category identity, for every category that captured content. The deploy groups a
    sound into the directory named by its category (structural capture already assigned it)."""
    mc = json.loads((HERE / "merged_channels.json").read_text())
    return {cat: cat for cat in sorted(mc) if mc[cat]["chosen"]}


def _build_source_height_map():
    """source path -> the height its source channel placed it at, AGGREGATED across every pack: if the same
    sound appears in several packs (or several channels) and some carry a height while others are 0, the
    highest non-zero wins. The structural folder-capture dropped height (a channel attribute, capture routes
    by folder), but the source configs still carry it - so a shipped sound keeps the ORIGINAL elevation its
    author gave it (overhead birds, high vents, thunder up top), and a pack that flattened height to 0 never
    overrides a pack that kept it. A sound in no channel anywhere stays 0 - no source height to recover."""
    hmap = {}
    for _name, gd in MODS:
        for _cn, cd in parse_channels(gd).items():
            h = None
            for ln in cd["settings"]:
                m = re.search(r"\bheight\s*=\s*(-?[\d.]+)", ln)
                if m:
                    h = float(m.group(1))
                    break
            if not h:                                  # no height line, or height 0 - nothing to recover
                continue
            h = int(h) if float(h).is_integer() else round(h, 2)
            for source_path in cd["sound_paths"]:            # sound paths are already ext-less, forward-slash (parse_channels)
                hmap[source_path] = h if source_path not in hmap else max(hmap[source_path], h)
    return hmap


def _build_source_band_map():
    """(pack, source path) -> (min_distance, max_distance, indoor): the SPAWN band the sound's source
    channel places it at - the pair vanilla update_ambient transforms (`random((max+min)/2, max)/2`
    outdoors, sound_ambient.script:127-129) - plus the channel's `indoor` flag driving the vanilla volume
    rule. This is the AUTHOR's placement, a different pair from the ogg blob's attenuation range. Keyed
    PER PACK: blob and band must come from the SAME author or the pair reproduces nobody's mix (a file
    shipped with pack A's short-range blob must not take pack B's far channel band - at pack B's distance
    it sits past its own blob max, an engine hard silence). Within one pack, a file wired at several bands
    keeps the LARGEST max (the author's own far usage wins over his close bed - his blob was made for
    both). Unwired sounds get no entry - the config writer resolves pool-first, then dup pools, then any
    pack, then the file's own blob pair."""
    bmap = {}
    for name, gd in MODS:
        for _cn, cd in parse_channels(gd).items():
            mn = mx = None
            indoor = False
            for ln in cd["settings"]:
                m = re.search(r"\bmin_distance\s*=\s*([\d.]+)", ln)
                if m:
                    mn = float(m.group(1))
                m = re.search(r"\bmax_distance\s*=\s*([\d.]+)", ln)
                if m:
                    mx = float(m.group(1))
                m = re.search(r"\bindoor\s*=\s*(\w+)", ln)
                if m:
                    indoor = m.group(1).lower() in ("true", "1", "yes", "on")
            if mn is None or mx is None or mx <= 0:
                continue
            if mx <= mn:
                mx = mn + 1.0
            for source_path in cd["sound_paths"]:
                key = (name, source_path)
                prev = bmap.get(key)
                if prev is None or mx > prev[1]:
                    bmap[key] = (mn, mx, indoor)
    return bmap


_MODS_RANK = {name: i for i, (name, _gd) in enumerate(MODS)}


def _resolve_band(bmap, entry):
    """The band for one shipped sound, same-author first: the winner pool's wiring, else a collapsed dup
    copy's own pool (that copy is the same recording, its pack's blob matched its band), else any pack that
    wires the path. EVERY cross-pack comparison follows the registry order (sources.py, ORDER IS
    LOAD-BEARING - the same preference dedup uses to pick the winning copy), so the dup candidates are
    ranked by it, not by their stored order. None -> the file's own blob pair at the call site."""
    band = bmap.get((entry["pool"], entry["source_path"]))
    if band:
        return band, "same-author"
    dups = sorted(entry.get("dups", ()), key=lambda d: _MODS_RANK.get(d[0], len(_MODS_RANK)))
    for pool, path in dups:
        band = bmap.get((pool, path))
        if band:
            return band, "dup-pack"
    for name, _gd in MODS:
        band = bmap.get((name, entry["source_path"]))
        if band:
            return band, "other-pack"
    return None, "unwired"


# Unwired sounds (no pack channel) get their CATEGORY's center band + this jitter, deterministic per name.
UNWIRED_JITTER = 0.25


def _name_jitter(name, frac):
    """Deterministic jitter in [-frac, frac] seeded by the deployed name, so a rebuild never reshuffles the
    unwired placements (a live random() would give every build a different corpus)."""
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    return (h / 0xffffffff * 2.0 - 1.0) * frac


def cmd_deploy(a):
    root = Path(a.root) if a.root else GDATA
    env = root / "configs/environment"
    snd = root / "sounds/zs"
    mc = json.loads((HERE / "merged_channels.json").read_text())
    cls = json.loads((HERE / "classification.json").read_text())
    ch_to_cat = build_effect_group_map()                 # source channel -> category
    effects = _build_layers(mc, cls, ch_to_cat)    # category -> [entries]
    _masterize_channels(effects)                # fold stereo -> mono FIRST (engine 3D-positions mono only)
    _dedupe_folded(effects)                      # collapse stereo files that fold to identical mono (veto-safe)
    _cull_dead(effects)                         # drop only DEAD files (unmeasurable / silent after the fold)

    if getattr(a, "wipe", True):
        _clean(snd)
    _clean(env / "ambients")
    _stamp_buckets(effects, snd)
    for stale in ("mod_sound_channels_alifespooks.ltx", "as_channel_layers.ltx"):
        (env / stale).unlink(missing_ok=True)      # old channel model, no longer written
    (root / "scripts" / "as_manifest.script").unlink(missing_ok=True)   # renamed to as_sound_config_gen

    # Emit each sound into our OWN category directory: zs\<category>\N.ogg. There is no engine
    # sound_channels.ltx for our content - the director reads as_sound_config_gen, not channels.
    for cat in sorted(effects):
        for e in effects[cat]:
            _emit_audio(e, snd / cat / e["bucket"] / f"{_deployed_name(e)}.ogg")

    # Resolve every sound's spawn band ONCE, from the AUTHOR blobs (before the floor is written): the
    # blob writer needs the band for the min floor, and the config writer must stamp the same values -
    # one resolution, no drift. Unwired sounds fall back to their own author blob pair and are flagged.
    hmap = _build_source_height_map()                        # recover each sound's ORIGINAL source-channel height
    bmap = _build_source_band_map()                          # (pack, path) -> the author's spawn band
    band_src = collections.Counter()
    review = []                                              # unwired sounds, flagged for hand review
    bands = {}                                               # id(entry) -> (ch_min, ch_max, indoor)
    for cat in sorted(effects):
        # pass 1: resolve wired bands + gather this category's blob pairs, to build the unwired center
        names, blobs, resolved, wired = {}, {}, {}, []
        for e in effects[cat]:
            n = _deployed_name(e)
            names[id(e)] = n
            ab = _read_blob((snd / cat / e["bucket"] / f"{n}.ogg").read_bytes()) or e.get("src_blob")
            blobs[id(e)] = (round(ab[0], 1), round(ab[1], 1)) if ab else (1.0, 100.0)
            band, how = _resolve_band(bmap, e)
            band_src[how] += 1
            resolved[id(e)] = band
            if band:
                wired.append(band)
        # UNWIRED band = the CATEGORY CENTER (robust median of the wired bands, or of the category's own blobs
        # when nothing in it is wired) + deterministic jitter, capped to each sound's own blob max. This
        # replaces the own-blob fallback (a default 1-300 blob flung a sound to 150m); the category center
        # places it where that category actually sits. Per-category + the blob-max cap = no cross-category
        # leak and no placement past a sound's silence point.
        src = [(b[0], b[1]) for b in wired] if wired else [blobs[id(e)] for e in effects[cat]]
        c_min = _median(sorted(s[0] for s in src))
        c_max = _median(sorted(s[1] for s in src))
        if c_max <= c_min:
            c_max = c_min + 1.0
        # pass 2: wired keep their band; unwired get the category center jittered, capped to blob max
        for e in effects[cat]:
            band = resolved[id(e)]
            if not band:
                n, (amn, amx) = names[id(e)], blobs[id(e)]
                j = 1.0 + _name_jitter(n, UNWIRED_JITTER)
                bmn, bmx = c_min * j, c_max * j
                if bmx > amx:                                # never place past this sound's own silence point
                    bmx = amx
                if bmn >= bmx:
                    bmn = bmx * 0.5
                band = (round(bmn, 1), round(bmx, 1), False)
                review.append((cat, n, e["pool"], e["source_path"], round(bmn, 1), round(bmx, 1)))
            bands[id(e)] = band

    _normalize_blobs(effects, snd, bands)    # author blob + the crest-inverted min floor against each band

    # as_sound_config_gen: category -> its sounds, each { path, blob_min, blob_max, height, ch_min, ch_max,
    # indoor }. The director reads THIS instead of sound_channels.ltx. Two distance pairs per sound, never
    # conflated: blob_min/blob_max = the ATTENUATION range from the deployed ogg blob (the engine's fade
    # curve, trace readout only); ch_min/ch_max = the source channel's SPAWN band - the pair vanilla
    # update_ambient transforms to place the sound (random((max+min)/2, max)/2 outdoors), recovered per
    # sound by _build_source_band_map + _resolve_band (same-author first), the file's own blob pair for
    # folder-only sounds (never a category median).
    # indoor = the channel's flag for the vanilla volume rule. height = the ORIGINAL source-channel
    # elevation (_build_source_height_map, highest non-zero wins). Anomaly Lua cannot list a directory at
    # runtime, so the sound list ships as data. No play rules here (env/requires/gates live in as_director).
    man = ["--- as_sound_config_gen: GENERATED by tools/build.py, do not edit. Category -> { dread bucket ->",
           "--- its sounds } for the director (read instead of sound_channels.ltx). Each row:",
           "--- { path, blob_min, blob_max, height, ch_min, ch_max, indoor } - blob pair = attenuation",
           "--- range (engine fade curve); ch pair = the source channel's SPAWN band vanilla's placement",
           "--- formula transforms; indoor = the channel flag for the vanilla volume rule.",
           "categories = {"]

    def _pack(cells, indent, budget=185):    # fill a line to <=budget chars then wrap (under the 200 cap)
        out, cur = [], ""
        for c in cells:
            add = (", " if cur else "") + c
            if cur and len(indent) + len(cur) + len(add) + 1 > budget:
                out.append(indent + cur + ",")
                cur = c
            else:
                cur += add
        if cur:
            out.append(indent + cur + ",")
        return out

    for cat in sorted(effects):
        by_bucket = {}
        for e in effects[cat]:
            n = _deployed_name(e)
            bk = e["bucket"]
            b = _read_blob((snd / cat / bk / f"{n}.ogg").read_bytes())
            mn, mx = (round(b[0], 1), round(b[1], 1)) if b else (1, 100)   # the DEPLOYED (floored) blob pair
            h = hmap.get(e["source_path"], 0)                 # aggregated source height (any pack), else 0
            bmn, bmx, ind = bands[id(e)]
            by_bucket.setdefault(bk, []).append(
                '{ "zs\\\\%s\\\\%s\\\\%s", %s, %s, %s, %s, %s, %s }' % (
                    cat, bk, n, mn, mx, h, round(bmn, 1), round(bmx, 1), "true" if ind else "false"))
        man.append('\t["%s"] = {' % cat)
        for bk in sorted(by_bucket):
            man.append('\t\t["%s"] = {' % bk)
            man += _pack(by_bucket[bk], "\t\t\t")
            man.append('\t\t},')
        man.append("\t},")
    man += ["}"]
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "as_sound_config_gen.script").write_text("\n".join(man) + "\n", encoding="utf-8")

    # Review list: every unwired sound (band = its own blob pair) flagged for hand evaluation - the
    # feed for a future hand-curated band table. Regenerated each deploy.
    (HERE / "band_review.tsv").write_text(
        "category\tdeployed\tpool\tsource_path\tband_min\tband_max\n" +
        "".join(f"{c}\t{n}\t{p}\t{sp}\t{a}\t{b}\n" for c, n, p, sp, a, b in review), encoding="utf-8")
    print(f"  bands: {band_src['same-author']} same-author, {band_src['dup-pack']} dup-pack, "
          f"{band_src['other-pack']} other-pack, {band_src['unwired']} unwired -> category center+jitter "
          f"(flagged in tools/band_review.tsv)")

    # Static DLTX veto overlay: remove our own sounds from the base ambient channels so the base never
    # doubles the director. Per-file removals across every scanned pack, matched by audio identity; bed
    # channels kept non-empty. Deterministic at config load - no runtime clone owns the muting.
    dltx, veto = _build_veto_overlay(effects)
    env = root / "configs" / "environment"
    env.mkdir(parents=True, exist_ok=True)
    (env / "mod_sound_channels_alifespooks.ltx").write_text(dltx, encoding="utf-8")

    if not getattr(a, "wipe", True):
        _remove_stale(snd, effects)
    print(f"deployed to {root}")
    print(f"  categories: {len(effects)}; sounds: {sum(len(v) for v in effects.values())}")
    print(f"  veto DLTX: {veto['removals']} removals across {veto['channels']} channels; "
          f"{veto['wired_removed']}/{veto['unique_paths']} shipped source-paths channel-wired and removed "
          f"({veto['folder_only']} folder-only, no base channel)")


# --- ledger (the content-hash proof: UNUSED-DARK must be 0) -------------------

# Weather (thunder/storm/pre_storm) and fog (tuman) are NOT in dark scope (dropped, base's job), so
# they are not expected in the capture and never count as UNUSED-DARK.
DARK_KW = ["spook", "spoop", "mutant", "scream", "distant", "amb_dark", "amb_night",
           "dark_amb", "ugrnd", "underground", "/metal", "banging", "rats", "drip",
           "/drone", "/noise", "whisper", "shooting", "wind_dark",
           "creep", "howl", "moan", "growl", "northern"]
EMISSION_KW = ["blowout", "psi_storm", "emission"]
INCLUDE_ROOTS = ["ambient", "ambience_exp", "nature", "anomaly"]


def cmd_ledger(a):
    mc = json.loads((HERE / "merged_channels.json").read_text())
    chosen = {}                                        # source hash -> (ch, source_path)
    for ch, c in _iterate_chosen(mc):
        chosen[hash_file(c["abs"])] = (ch, c["source_path"])
    deployed = set()                                   # AUDIO hashes actually shipped - n108
    zs = GDATA / "sounds/zs"                            # rewrites comment headers, so a shipped
    for f in zs.rglob("*.ogg"):                         # file's BYTES differ from source while its
        deployed.add(_hash_audio(f))                    # audio does not; match blob-agnostic.
    ip = HERE / "intra_dups.json"                       # our own re-encodes the PCM dedup dropped
    intra_dropped = set(json.loads(ip.read_text())) if ip.exists() else set()
    def _load_set(fn):
        p = HERE / fn
        return set(json.loads(p.read_text())) if p.exists() else set()
    silence_dropped = _load_set("silence_dropped.json") # dropped as dead/empty (true peak -inf)
    longfile_culled = _load_set("longfile_culled.json") # dropped: active length > MAX_ACTIVE_S
    sliced_dropped  = _load_set("sliced_dropped.json")  # dark_signal originals replaced by sliced pieces
    rows, counts, pending = [], collections.Counter(), []
    for name, gd in MODS:
        if name == "vanilla":
            continue
        sroot = Path(gd) / "sounds"
        if not sroot.is_dir():
            continue
        for f in sorted(sroot.rglob("*.ogg")):
            rel = f.as_posix().split("/sounds/")[-1]
            low = rel.lower()
            h = hash_file(f)
            dark = any(k in low for k in DARK_KW)
            emission = any(k in low for k in EMISSION_KW)
            excluded = any(x in low for x in EXCLUDE)   # intentionally out-of-scope trees (ambience_exp, ...)
            under_root = low.split("/", 1)[0] in INCLUDE_ROOTS
            if _hash_audio(f) in deployed:
                st = "USED-shipped"
            elif h in chosen:                           # a chosen sound whose audio isn't in the tree
                st = "USED-effect-unshipped"
            elif emission:
                st = "EMISSION-excluded"
            elif excluded:
                st = "EXCLUDED-scope"
            elif h in intra_dropped:                    # our own re-encode, deduped by cross-correlation
                st = "INTRA-DUP-excluded"
            elif h in silence_dropped:                  # dead/empty, dropped by the silence gate
                st = "SILENCE-excluded"
            elif h in longfile_culled:                  # active length over the cap, culled
                st = "LONGFILE-culled"
            elif h in sliced_dropped:                   # dark_signal original, replaced by sliced pieces
                st = "SLICED-excluded"
            elif dark and under_root:
                info = sp.probe(str(f)) or {}
                if info.get("sample_rate") != 44100:
                    st = "OFFSPEC-48k-excluded"
                else:
                    pending.append((name, rel, f))      # decide UNUSED-DARK vs INTRA-DUP acoustically
                    continue
            elif under_root:
                st = "off-scope-or-dup"
            else:
                st = "SKIP-nonambient"
            rows.append(f"{name}\t{rel}\t{st}")
            counts[st] += 1
    # a dark file we didn't byte-match may still be a re-encoded copy of one WE ship that the PCM
    # dedup dropped (INTRA-DUP, captured-then-deduped, not missed). Fingerprint the residue against
    # our chosen set so UNUSED-DARK counts only TRUE misses (a net-new dark sound left uncaptured).
    chosen_fp = sp.pmap(lambda a: (sp.fingerprint(a, FP_LEN),
                                   round(float((sp.probe(a) or {}).get("duration") or 0))),
                        [c["abs"] for _ch, c in _iterate_chosen(mc)], sp.DEF_JOBS)
    chosen_by_dur = collections.defaultdict(list)
    for fp, dur in chosen_fp:
        if fp:
            chosen_by_dur[dur].append(fp)

    def _fp(item):
        _name, _rel, path = item
        return (sp.fingerprint(str(path), FP_LEN), round(float((sp.probe(str(path)) or {}).get("duration") or 0)))
    for (name, rel, _f), (fp, dur) in zip(pending, sp.pmap(_fp, pending, sp.DEF_JOBS)):
        st = "UNUSED-DARK"
        if fp:
            ds = (dur - 1, dur, dur + 1)
            if any(sp.fp_similarity(fp, b) >= BASE_SIM for d in ds for b in chosen_by_dur.get(d, ())):
                st = "INTRA-DUP-excluded"
        rows.append(f"{name}\t{rel}\t{st}")
        counts[st] += 1
    (HERE / "ledger.tsv").write_text("pack\tfile\tstatus\n" + "\n".join(rows) + "\n", encoding="utf-8")
    for st, n in counts.most_common():
        print(f"{n:6d}  {st}")
    print(f"UNUSED-DARK = {counts['UNUSED-DARK']}   (MUST be 0)")


# --- provenance (n070: every shipped N.ogg -> what it is and where from) ------

def _parse_settings(lines):
    out = {}
    for ln in lines:
        m = re.match(r"\s*(min_distance|max_distance|period0|period1|period2|period3|height|indoor)\s*=\s*(\S+)", ln)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _map_channel_sections():
    """source channel -> sorted list of 'pack:presetfile:section' it played in."""
    out = collections.defaultdict(set)
    for name, gd in MODS:
        for fname, secs in parse_presets(gd).items():
            for sec, d in secs.items():
                for ch in d["dynamic"]:
                    out[ch].add(f"{name}:{fname[:-4]}:{sec}")
    return {k: sorted(v) for k, v in out.items()}


def cmd_provenance(a):
    mc = json.loads((HERE / "merged_channels.json").read_text())
    cls = json.loads((HERE / "classification.json").read_text())
    ch_to_cat = build_effect_group_map()
    effects = _build_layers(mc, cls, ch_to_cat)
    _masterize_channels(effects)      # SAME fold deploy applies, so the mono-hash names match the tree
    _dedupe_folded(effects)           # SAME collapse deploy applies, so the row set matches the tree
    _cull_dead(effects)               # SAME drop deploy applies, so the N-numbering matches the tree
    zs = (Path(a.root) if getattr(a, "root", None) else GDATA) / "sounds/zs"   # honor --root like deploy
    _stamp_buckets(effects, zs)                                                # e['bucket'] from the deployed tree

    # Structural capture: a sound's origin is its SOURCE PATH (orig_dir/orig_file from the source path) + the
    # pack it came from. No channel/settings/sections columns - categories are not channels. min/max/
    # base_volume live in the deployed ogg blob. The audio self-verify is the preservation proof.
    cols = ["deployed", "category", "orig_mod", "orig_dir", "orig_file", "base_volume"]
    rows, verify_ok, verify_bad = [], 0, 0
    for cat in sorted(effects):                       # every sound deploys to zs\<category>\<name>
        for e in effects[cat]:
            n = _deployed_name(e)
            dep = f"zs\\{cat}\\{e['bucket']}\\{n}"
            source_path = e["source_path"]
            dfile = zs / cat / e["bucket"] / f"{n}.ogg"
            bv = ""
            if dfile.exists():
                b = _read_blob(dfile.read_bytes())
                if b:
                    bv = round(b[2], 3)
                if _hash_audio(dfile) == _hash_audio(Path(e["abs"])):
                    verify_ok += 1
                else:
                    verify_bad += 1
            rows.append([dep, cat, e["pool"], str(Path(source_path).parent).replace("\\", "/"),
                         Path(source_path).name, str(bv)])
    lines = ["\t".join(cols)] + ["\t".join(str(x) for x in r) for r in rows]
    (HERE / "provenance.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"provenance: {len(rows)} shipped sounds -> provenance.tsv")
    print(f"audio self-verify vs source (comment-blob-agnostic): {verify_ok} match, {verify_bad} MISMATCH")
    if verify_bad:
        print("  MISMATCH != 0 -> the deploy ordering does NOT reproduce the tree; provenance is NOT exact.")


def _drop_frozen_reencodes(new_merged):
    """Drop any net-new sound that is a re-encode / near-clone of an already-PUBLISHED sound - a different
    audio hash (so the exact-hash check missed it) but fp + PCM xcorr confirm the same recording. This is
    dedupe's stages 2-3 run against the frozen corpus instead of within the pool. Bounded: only each
    category's DEPLOYED files whose duration is within 1s of a candidate are fingerprinted, so a rare add
    stays cheap. Frozen always wins - a match drops the NEW file, the published one is never touched."""
    total = 0
    for cat, d in new_merged.items():
        cands = d["chosen"]
        fdir = SND / cat
        if not cands or not fdir.is_dir():
            continue
        frozen = sorted(str(path) for path in fdir.glob("*.ogg"))
        if not frozen:
            continue
        _dur = lambda a: round(float((sp.probe(a) or {}).get("duration") or 0))
        cabs = [c["abs"] for c in cands]
        cdur = dict(zip(cabs, sp.pmap(_dur, cabs, sp.DEF_JOBS)))
        fdur = dict(zip(frozen, sp.pmap(_dur, frozen, sp.DEF_JOBS)))
        want = {x for cd in cdur.values() for x in (cd - 1, cd, cd + 1)}
        frel = [f for f in frozen if fdur[f] in want]          # only plausibly same-length published files
        if not frel:
            continue
        cfp = dict(zip(cabs, sp.pmap(lambda a: sp.fingerprint(a, FP_LEN), cabs, sp.DEF_JOBS)))
        ffp = dict(zip(frel, sp.pmap(lambda a: sp.fingerprint(a, FP_LEN), frel, sp.DEF_JOBS)))
        keep = []
        for c in cands:
            a = c["abs"]
            hit = False
            for f in frel:
                if cfp[a] and ffp[f] and abs(cdur[a] - fdur[f]) <= 1 \
                        and sp.fp_similarity(cfp[a], ffp[f]) >= BASE_SIM \
                        and sp.pcm_correlation(sp.decode_pcm(a), sp.decode_pcm(f)) >= DEDUP_XCORR:
                    hit = True
                    break
            if hit:
                total += 1
            else:
                keep.append(c)
        new_merged[cat]["chosen"] = keep
    if total:
        print(f"frozen re-encode dedup: dropped {total} net-new that re-encode an already-published sound")
    return total


def _ingest_source(name, gd):
    """Fold ONE new source over the frozen published corpus and append the net-new to merged_channels.json;
    return the net-new count. Nothing already shipped is renamed or re-hashed. Dedup covers exact reships
    (audio hash) and re-encodes (fp + PCM xcorr) vs the frozen corpus, plus md5+fp+xcorr within the source.
    Each net-new file keeps its author's own blob, so an add never shifts a published file's loudness."""
    mc = json.loads((HERE / "merged_channels.json").read_text())
    # Frozen identity = the audio hashes of the CORPUS OF RECORD (existing merged_channels.json entries),
    # NOT the deployed files. A sound that survives dedup but is culled at deploy (dead / silent after fold) is
    # still recorded here, so keying on the record makes a re-add IDEMPOTENT: it can never regrow the corpus
    # by re-proposing a culled sound (keying on deployed files missed the culled ones and looped forever).
    # Computed once in parallel. An empty record (fresh install) gives an empty frozen set, so `add` over
    # nothing is a from-scratch build.
    existing = [c["abs"] for cat0 in mc for c in mc[cat0]["chosen"]]
    frozen = set(sp.pmap(lambda path: _try_hash_audio(Path(path)), existing, sp.DEF_JOBS)) - {None}
    pool = collections.defaultdict(list)
    audit = collections.defaultdict(collections.Counter)
    offrate, out_scope = _scan_source(name, gd, pool, audit)
    new_merged, n_dup = {}, 0
    for cat, files in pool.items():
        keep = []
        for c in dedupe(files):
            ah = _try_hash_audio(Path(c["abs"])) or hash_file(c["abs"])
            if ah in frozen:                                   # already in the corpus of record - never re-add
                n_dup += 1
                continue
            keep.append({"abs": c["abs"], "source_path": c["source_path"], "pool": c["pool"], "hash": c["hash"],
                         "bitrate": c["bitrate"], "channels": c["channels"], "dur": c.get("dur", 0.0),
                         "dups": c.get("dups", [])})
        if keep:
            new_merged[cat] = {"chosen": keep}
    _drop_silent(new_merged)                                  # the same net-new gates the full plan applies
    _dedupe_across_channels(new_merged)
    _cull_long_files(new_merged)
    _drop_frozen_reencodes(new_merged)                         # drop re-encodes/near-clones of published sounds
    n_new = 0
    for cat, d in new_merged.items():
        mc.setdefault(cat, {"chosen": []})["chosen"].extend(d["chosen"])
        n_new += len(d["chosen"])
    (HERE / "merged_channels.json").write_text(json.dumps(mc, indent=1), encoding="utf-8")
    print(f"\nadd {name}: +{n_new} net-new ({n_dup} already published; off-44100 {offrate}; "
          f"out-of-scope {out_scope})")
    return n_new


def cmd_add(a):
    """Incremental, NON-WIPING build. `add <Source> <path>` ingests one new source (net-new -> <cat>/all/);
    `add` with no source just re-syncs the config from the current tree, applying your dread-bucket moves.
    Never wipes zs/, so curation (files moved into low/med/high) is preserved. Run `rebuild` before a release
    to refresh the ledger + provenance proofs."""
    name, gd = getattr(a, "name", None), getattr(a, "gd", None)
    n_new = _ingest_source(name, gd) if (name and gd) else 0
    import types
    ns = types.SimpleNamespace(out=None, root=getattr(a, "root", None), wipe=False)
    if n_new:
        print("\n========== classify =========="); cmd_classify(ns)
    print("\n========== deploy (no wipe - dread buckets preserved) =========="); cmd_deploy(ns)
    print(f"add: +{n_new} net-new deployed; config re-synced from the tree. "
          f"Run `rebuild` before release to refresh ledger + provenance.")


def cmd_provision(a):
    """Check every registry source is present locally. Sources are always pulled by hand - the pipeline
    never downloads (url is a reference/credit link only). Reports OK/MISSING using the SAME capture the build
    does (`<path>/sounds/*.ogg`), so a source that would be silently skipped shows up here. Run before a build."""
    sources.check_licences()
    missing = []
    for s in sources.SOURCES:
        snd = Path(s["path"]) / "sounds"
        if snd.is_dir() and any(snd.rglob("*.ogg")):
            print(f"  OK      {s['name']:20s} {s['path']}")
        else:
            missing.append(s["name"])
            print(f"  MISSING {s['name']:20s} {s['path']}   (ref: {s['url'] or 'none'})")
    if missing:
        print(f"\n{len(missing)} MISSING - pull them locally before building: {', '.join(missing)}")
    else:
        print("\nall sources present - `build.py all` reproduces the corpus.")


def cmd_rebuild(a):
    """FULL rebuild from scratch: plan -> classify -> loudness -> deploy -> ledger -> provenance. Wipes zs/
    and re-emits the whole corpus into <cat>/all/ (resets dread curation - RARE, deliberate). One command so
    the sequence (and the classify-after-plan rule) can never be got wrong. Use `add` for the curation-safe
    incremental path."""
    import types, time
    sources.check_licences()                          # never build with an uncleared source (licence=pending)
    ns = types.SimpleNamespace(out=None, root=getattr(a, "root", None))
    timings = []
    t_all = time.perf_counter()
    for name, fn in (("plan", cmd_plan), ("classify", cmd_classify), ("loudness", cmd_loudness),
                     ("deploy", cmd_deploy), ("ledger", cmd_ledger), ("provenance", cmd_provenance)):
        print(f"\n========== {name} ==========")
        t0 = time.perf_counter()
        fn(ns)
        dt = time.perf_counter() - t0
        timings.append((name, dt))
        print(f"[time] {name}: {dt:.1f}s")
    total = time.perf_counter() - t_all
    print("\n========== done ==========")
    print("stage timings (slowest first, so you know where to optimize):")
    for name, dt in sorted(timings, key=lambda kv: -kv[1]):
        print(f"  {name:11s} {dt:8.1f}s  {(100 * dt / total if total else 0):5.1f}%")
    print(f"  {'TOTAL':11s} {total:8.1f}s")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan").set_defaults(func=cmd_plan)
    p = sub.add_parser("classify"); p.add_argument("--out"); p.set_defaults(func=cmd_classify)
    p = sub.add_parser("loudness"); p.add_argument("--out"); p.set_defaults(func=cmd_loudness)
    p = sub.add_parser("deploy"); p.add_argument("--root"); p.set_defaults(func=cmd_deploy)
    p = sub.add_parser("add"); p.add_argument("name", nargs="?"); p.add_argument("gd", nargs="?"); p.add_argument("--root"); p.set_defaults(func=cmd_add)
    sub.add_parser("ledger").set_defaults(func=cmd_ledger)
    sub.add_parser("provenance").set_defaults(func=cmd_provenance)
    sub.add_parser("provision").set_defaults(func=cmd_provision)
    p = sub.add_parser("rebuild"); p.add_argument("--root"); p.set_defaults(func=cmd_rebuild)
    a = ap.parse_args(); a.func(a)
