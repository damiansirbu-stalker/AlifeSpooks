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
    ("lar_crow", "wildlife"), ("lar_dog", "wildlife"), ("lar_owls", "wildlife"), ("lar_pigeon", "wildlife"),
    ("lar_wolf", "wildlife"), ("lar_frog", "wildlife"),
    ("lar_tree", "foliage"), ("lar_wind", "wind"),
    ("howling_wind", "wind"), ("howling", "wildlife"),         # wind-first so howling_wind != animal howl
]


def route(path):
    """Structural per-file category routing (n117): a source path -> a category name, or None to drop.
    Whole-tree allowlist by folder, not keyword matching on the filename. Order: exclusions, zone-mutant
    ambience, the creature pool, then the flat ambience allowlist (first match wins)."""
    p = path.replace("\\", "/").lower()
    if any(x in p for x in EXCLUDE):
        return None
    # zone-mutant ambience: ONLY the terrain-split trx/spooks_above/<zone>{day,night}mutants (validated
    # horror). The soundscape/background/<Terrain> beds were user-checked and rejected (birds/generic, no
    # horror), so they are NOT routed here - the zones are pure zone-mutant content.
    for z in ZONES:
        if z + "daymutants" in p or z + "nightmutants" in p:
            return "mutant_ambient_" + z
    # creature pool. wolf/mwolf are eerie wildlife, not creatures. monsters/<sp> is a creature-sound tree
    # with COMBAT mixed in, so MUTANT_KEEP filters out attack/hit/die there. soundscape/mutants and the flat
    # spooks_above/mutants are ALREADY ambient/distant dread (named sound_NN), so keep them all - no filter.
    if "/wolf/" in p or "/mwolf/" in p:
        return "wildlife"
    if "/monsters/" in p:
        return "mutant" if MUTANT_KEEP.search(p) else None
    if "/soundscape/mutants/" in p or "spooks_above/mutants" in p:
        return "mutant"
    return next((c for sub, c in ROUTE if sub in p), None)

# Source packs, assessed by hand before wiring. Capture is STRUCTURAL per-file (ROUTE, below): each
# pack's folder trees map to categories by path, so the whole horror tree is pulled, not just the
# files a channel wires. n117: +DS Amplified Vanilla / 457 RETUNE / 304 Dark Signal Weather; the drops
# (DS Overhaul Atmospherics, RE-TUNE Ambience, 274 bullet SFX) are simply not listed. Doom II NSDARK
# deferred (n116). vanilla stays last for portability coverage only.
MODS = [
    ("Amplified",      "C:/Users/damian/Downloads/anomaly_audio_mods/Dark Signal Amplified Soundscape/gamedata"),
    ("AmplifiedVanilla", "C:/Users/damian/Downloads/anomaly_audio_mods/DS Amplified Vanilla/gamedata"),
    ("Soundscape",     "D:/Games/GAMMA/GAMMA/mods/3- Soundscape Overhaul - Solarint/gamedata"),
    ("RETUNE457",      "D:/Games/GAMMA/GAMMA/mods/457- RETUNE Ambiant Sounds - Aphrodite_child/gamedata"),
    ("DarkSignal304",  "D:/Games/GAMMA/GAMMA/mods/304- Dark Signal Weather and Ambiance Audio - Shrike/gamedata"),
    # myRETUNE Antares (user-vouched): the same soundscape/underground/spooks_above|below dread tree.
    ("myRETUNE",       "C:/Users/damian/Downloads/anomaly_audio_mods/myRETUNE_AntaresWolverine_2.1/myRETUNE ambience sounds ver2.1/gamedata"),
    # net-new distant-creature calls under soundscape/mutants.
    ("RealDistantMutants", "C:/Users/damian/Downloads/anomaly_audio_mods/Real Distant Mutants Sounds/gamedata"),
    # 276 creature-sound pack: routed to the mutant pool, near-lurking dread only (combat filtered out).
    ("DSMutants",      "C:/Users/damian/Downloads/anomaly_audio_mods/276- Dark Signal Mutants Audio - Shrike/gamedata"),
    # net-new underground dread + the terrain-split zone-mutant trees (trx/spooks_above/<zone>mutants).
    ("AudioExpansion", "C:/Users/damian/Downloads/anomaly_audio_mods/Audio Expansion/gamedata"),
    # Standalone/spinoff STALKER builds mined for dread sources (doc: anomaly_audio_mods/STANDALONE_BUILDS.md).
    # gd points at the extracted root (holds sounds/); SoC-lineage, so most content dedups to the game core.
    ("DeadAir",   "C:/Users/damian/Downloads/stalker_versions_for_sound/_unpacked/DeadAir"),
    ("OGSE",      "C:/Users/damian/Downloads/stalker_versions_for_sound/_unpacked/OGSE"),
    ("Prosector", "C:/Users/damian/Downloads/stalker_versions_for_sound/_unpacked/Prosector"),
    ("Solyanka",  "C:/Users/damian/Downloads/stalker_versions_for_sound/_unpacked/solyanka"),
    ("NLC",       "C:/Users/damian/Downloads/stalker_versions_for_sound/_unpacked/NLC"),
    ("SoP",       "C:/Users/damian/Downloads/stalker_versions_for_sound/_unpacked/sop"),
    # Broader dark baseline from the audio-mod pool (dedup grounding = "what we already have").
    ("DarkSignal274",     "C:/Users/damian/Downloads/anomaly_audio_mods/274- Dark Signal Audio Pack - Shrike/gamedata"),
    ("DarkSignal285",     "C:/Users/damian/Downloads/anomaly_audio_mods/285- Dark Signal Blowout and Anomalies Audio - Shrike/gamedata"),
    ("AmbientExtended",   "C:/Users/damian/Downloads/anomaly_audio_mods/Ambient Extended Reworked/gamedata"),
    ("ImmersiveAmbience", "C:/Users/damian/Downloads/anomaly_audio_mods/Immersive Ambience Expansion/gamedata"),
    # Shrike's unreleased Dark Signal interior audio, given directly (granted 2026-08-15, see doc/licensing.md).
    ("ShrikeInterior", "C:/Users/damian/Downloads/anomaly_audio_mods/Dark Signal Unused Interior - Shrike/gamedata"),
    ("vanilla",        "D:/Games/GAMMA/Anomaly/tools/_unpacked"),
]

HERE = Path(__file__).resolve().parent


def parse_channels(gamedata):
    """channel(lower) -> {settings:[raw non-sounds lines], stems:[sound stems]}.
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
                ch.setdefault(cur, {"settings": [], "stems": []})
                continue
            if cur is None:
                continue
            if "sounds" in code and "=" in code:
                for t in code.split("=", 1)[1].split(","):
                    t = t.strip().replace("\\", "/")
                    if t and "no_sound" not in t:
                        ch[cur]["stems"].append(t)
            elif code.strip():
                ch[cur]["settings"].append(raw.rstrip())
    return ch


def resolve(stem, sounds_root):
    p = Path(sounds_root) / (stem + ".ogg")
    return p if p.exists() else None


def file_hash(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def dedup_pick(files):
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
    # 1. exact byte dedup
    by_md5 = {}
    for f in files:
        f["hash"] = file_hash(f["abs"])
        by_md5.setdefault(f["hash"], []).append(f)
    reps = [max(g, key=lambda f: f["bitrate"]) for g in by_md5.values()]
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
                chosen.append(max(g, key=lambda f: f["bitrate"]))
    good = [c for c in chosen if c["bitrate"] >= LOWQ_BITRATE]
    return good if good else chosen


# --- routing / layer-map inputs: what the base install PLAYS -----------------
# We do NOT dedup against any target modpack: a sound is never dropped because the
# install already plays it. Doubling is handled at RUNTIME by the base-veto (as_director
# mutes the base's copy of a sound we ship, keyed off as_blockdata). _active_channels is
# kept only to resolve which channels a config plays, for the base dark-channel layer map
# and channel routing. Source-side waveform dedup (dedup_pick) is unaffected.
VAN_CFG = "D:/Games/GAMMA/Anomaly/tools/_unpacked"
GAMMA_WINNER = "D:/Games/GAMMA/GAMMA/mods/304- Dark Signal Weather and Ambiance Audio - Shrike/gamedata"
FP_LEN = 30
BASE_SIM = 0.88     # Chromaprint recall threshold: >= this makes a pair a same-sound CANDIDATE
DEDUP_XCORR = 0.90  # PCM cross-correlation DECIDER: >= this confirms a candidate is the same
                    # recording (a re-encode). Below it the pair is kept as distinct variety.
# Loudness normalization (Dark Signal Amplified reference: median peak ~-1 dB). Each kept file's
# base_volume in its ogg blob is set so its true peak lands at TARGET_PEAK_DB - lossless, no re-encode.
# A file whose peak is below CULL_PEAK_DB cannot reach target without absurd gain (amplified noise, not
# a real quiet sound), so it is DROPPED, not shipped. No near-silent files survive.
TARGET_PEAK_DB = -1.0
CULL_PEAK_DB   = -30.0
# astats reads the FLOAT-decoded samples, and a handful of vorbis decode outliers can report an
# impossible peak (measured +42..+82 dB on files that peak at 0 dBFS per volumedetect, Peak count=2).
# _norm_bv would turn that into a ~0 base_volume and ship the file SILENT. A peak above this ceiling is
# not a real inter-sample overshoot (those stay under ~+6 dB) - clamp it to the 0 dBFS physical ceiling.
PEAK_FLOAT_CEILING = 12.0
                    # Frozen as validated (MANGLE=0); see architecture.md I3.
# Long-file handling (n117): a sound whose ACTIVE (silence-removed) length exceeds the max emission tick
# outlives its slot and overlaps the next fire, so it is CULLED - EXCEPT dark_signal, which is SLICED into
# <=MAX_ACTIVE_S desilenced pieces (keeps the loved 4-min radio as clean pieces). Sliced/desilenced files
# re-encode -> lose the source X-Ray blob -> get the category-median blob at deploy (the one I5 exception).
MAX_ACTIVE_S     = 20.0
SILENCE_NOISE_DB = "-30dB"
SILENCE_MIN_S    = 0.5
SLICE_DIR        = HERE / "_sliced"


def _active_channels(gd):
    """channels PLAYED in a preset (static sound_channels + dynamic) on this install."""
    a = set()
    for _f, secs in parse_presets(gd).items():
        for _s, d in secs.items():
            a |= {c.lower() for c in d.get("base", [])} | {c.lower() for c in d.get("dynamic", [])}
    return a


def _cross_channel_dedup(merged):
    """Drop byte-identical copies of a recording a source pack listed in more than one
    channel. md5-exact ONLY - a hash match is provably the same file, so no distinct
    sound can be lost (no fingerprint judgment, unlike _base_dedup). Keep one home per
    recording (first channel it appears in); never empty a channel."""
    seen = {}
    n_drop = 0
    for chan in merged:
        keep, dup = [], []
        for c in merged[chan]["chosen"]:
            h = file_hash(c["abs"])
            if seen.get(h, chan) == chan:
                seen[h] = chan
                keep.append(c)
            else:
                dup.append(c)                      # byte-identical to a home in another channel
        if not keep and dup:                       # never-empty: rescue one as this channel's home
            keep.append(dup.pop(0))
        n_drop += len(dup)
        merged[chan]["chosen"] = keep
    print(f"cross-channel dedup: dropped {n_drop} byte-identical copies (md5-exact, one home each)")


def _silence_gate(merged):
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
        json.dumps(sorted({file_hash(a) for a in dead})), encoding="utf-8")
    n = 0
    for chan in merged:
        before = len(merged[chan]["chosen"])
        merged[chan]["chosen"] = [c for c in merged[chan]["chosen"] if c["abs"] not in dead]
        n += before - len(merged[chan]["chosen"])
    print(f"silence gate: dropped {n} dead/empty files (true peak -inf, quiet sounds kept)")


def _loudness_cull(effects):
    """Measure each source's true peak. DROP any file that cannot reach TARGET_PEAK_DB without absurd
    gain (peak <= CULL_PEAK_DB, or unmeasurable/silent - that is amplified noise, not a quiet sound),
    and store the peak on each survivor so deploy can write a normalizing base_volume. Mutates effects."""
    import subprocess, re
    def peak(a):
        r = subprocess.run([sp.tool("ffmpeg"), "-i", a, "-af", "astats=metadata=1:reset=0",
                            "-f", "null", "-"], capture_output=True, text=True)
        m = re.search(r"Peak level dB:\s*(\S+)", r.stderr)
        if not m or m.group(1) == "-inf":
            return None
        try:
            p = float(m.group(1))
        except ValueError:
            return None
        return 0.0 if p > PEAK_FLOAT_CEILING else p
    paths = list({e["abs"] for cat in effects for e in effects[cat]})
    pk = dict(zip(paths, sp.pmap(peak, paths, sp.DEF_JOBS)))
    dropped = 0
    for cat in effects:
        kept = []
        for e in effects[cat]:
            p = pk.get(e["abs"])
            if p is None or p <= CULL_PEAK_DB:
                dropped += 1
            else:
                e["peak"] = p
                kept.append(e)
        effects[cat] = kept
    print(f"loudness cull: dropped {dropped} files (peak <= {CULL_PEAK_DB} dB or silent)")


def _active_seconds(abs_path, duration):
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


def _long_file_pass(merged):
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
            active = _active_seconds(c["abs"], float(c.get("dur") or 0.0))
            if active <= MAX_ACTIVE_S:
                new_chosen.append(c)
            elif cat == "dark_signal":
                sliced_orig.append(c["hash"])
                for p in _slice_file(Path(c["abs"]), SLICE_DIR / cat, Path(c["stem"]).name):
                    sliced_to += 1
                    piece = dict(c)
                    piece.update(abs=str(p), stem=Path(c["stem"]).as_posix() + "#" + p.stem,
                                 hash=file_hash(p), cut=True)
                    new_chosen.append(piece)
            else:
                culled.append(c["hash"])
        merged[cat]["chosen"] = new_chosen
    (HERE / "longfile_culled.json").write_text(json.dumps(sorted(set(culled))), encoding="utf-8")
    (HERE / "sliced_dropped.json").write_text(json.dumps(sorted(set(sliced_orig))), encoding="utf-8")
    print(f"long-file pass: culled {len(culled)} (active > {int(MAX_ACTIVE_S)}s); "
          f"sliced {len(sliced_orig)} dark_signal -> {sliced_to} pieces")


def cmd_plan(_):
    # STRUCTURAL per-file capture (n117): walk every pack's sound tree, route each file to a category by
    # its FOLDER PATH (route), gate on 44100, pool by category. No channel parsing - the packs ship far
    # more dark content than they wire, so the folder trees are the source of truth. Unmatched files are
    # dropped (dark scope, I9); the folder audit proves no generic folder leaked in.
    pool = collections.defaultdict(list)                        # category -> [file dicts]
    audit = collections.defaultdict(collections.Counter)       # category -> {source_folder: count}
    offrate = dropped_scope = 0
    for name, gd in MODS:
        sroot = Path(gd) / "sounds"
        if not sroot.is_dir():
            continue
        for f in sorted(sroot.rglob("*.ogg")):
            cat = route(f.as_posix())
            if not cat:
                dropped_scope += 1
                continue
            info = sp.probe(str(f)) or {}
            if info.get("sample_rate") != 44100:               # X-Ray fitness: 44100 only
                offrate += 1
                continue
            rel = f.as_posix().split("/sounds/", 1)[-1]
            pool[cat].append({"abs": str(f), "stem": rel[:-4], "pool": name,
                              "bitrate": info.get("bit_rate", 0), "channels": info.get("channels", 0),
                              "dur": info.get("duration") or 0.0})
            audit[cat][name + ":" + str(Path(rel).parent)] += 1

    # dedup per category (source-side waveform), then silence + cross-category dedup
    merged = {}
    tot_in = tot_kept = 0
    kept_hashes = set()
    for cat in CATEGORIES:
        files = pool.get(cat, [])
        tot_in += len(files)
        chosen = dedup_pick(files) if files else []
        kept_hashes |= {c["hash"] for c in chosen}
        tot_kept += len(chosen)
        merged[cat] = {
            "chosen": [{"abs": c["abs"], "stem": c["stem"], "pool": c["pool"], "hash": c["hash"],
                        "bitrate": c["bitrate"], "channels": c["channels"], "dur": c.get("dur", 0.0)}
                       for c in chosen],
        }
    # Intra-corpus re-encodes the PCM dedup dropped: their hashes, so the ledger books them as
    # captured-then-deduped, not a coverage miss (md5-losers share the winner's hash, already in kept).
    pool_hashes = {f["hash"] for fs in pool.values() for f in fs if "hash" in f}
    (HERE / "intra_dups.json").write_text(json.dumps(sorted(pool_hashes - kept_hashes)), encoding="utf-8")
    # No target-modpack dedup. Doubling with the base is handled at config load by the static DLTX veto.
    _silence_gate(merged)
    _cross_channel_dedup(merged)
    _long_file_pass(merged)                    # cull active > 20s; slice dark_signal into desilenced pieces
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


def _iter_chosen(mc):
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
    return {"ch": chan, "stem": c["stem"], "dur": dur, "cen": cen, "flat": flat,
            "crest": round(crest, 1), "bright": bright, "tone": tone}


def cmd_classify(a):
    mc = json.loads((HERE / "merged_channels.json").read_text())
    items = list(_iter_chosen(mc))
    out = sp.pmap(lambda t: _classify_one(*t), items, sp.DEF_JOBS)
    dst = Path(a.out) if a.out else (HERE / "classification.json")
    dst.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"classified {len(out)} sounds (all one-shot effects) -> {dst.name}")


# --- loudness (per-group median leveling, outliers only) ---------------------

def _lufs_one(abs_):
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
    items = list(_iter_chosen(mc))
    lufs = sp.pmap(lambda t: (t[0], t[1]["stem"], _lufs_one(t[1]["abs"])), items, sp.DEF_JOBS)
    by_ch = collections.defaultdict(list)
    for ch, stem, L in lufs:
        if L is not None:
            by_ch[ch].append((stem, L))
    outliers = []
    for ch, rows in by_ch.items():
        vals = sorted(L for _, L in rows)
        med = _median(vals)
        q1 = _median(vals[:len(vals) // 2])
        q3 = _median(vals[(len(vals) + 1) // 2:])
        band = max(6.0, 1.5 * (q3 - q1))
        for stem, L in rows:
            if abs(L - med) > band:
                outliers.append({"ch": ch, "stem": stem, "gain_db": round(med - L, 1)})
    dst = Path(a.out) if a.out else (HERE / "loudness_outliers.json")
    dst.write_text(json.dumps(outliers, indent=1), encoding="utf-8")
    print(f"loudness: {len(outliers)} outliers ({100*len(outliers)//max(1,len(lufs))}%) to gain -> {dst.name}")


# --- deploy (deterministic: reproduces the N numbering from the JSONs) --------

def _build_layers(mc, cls, ch_to_group):
    """Group every chosen sound into its director CATEGORY (the shipped directory), deterministically.
    classification.json is produced by classifying _iter_chosen(mc) in order, so cls[i] IS the
    classification of the i-th chosen entry - align POSITIONALLY, not by (ch,stem). Two chosen
    entries can share a stem (distinct sounds a pack shipped under one filename that PCM proved
    different); a (ch,stem) lookup collapsed them. Positional alignment ships each exactly once."""
    chosen_seq = list(_iter_chosen(mc))
    assert len(cls) == len(chosen_seq), (
        f"classification.json ({len(cls)}) out of sync with merged_channels.json "
        f"({len(chosen_seq)}); rerun classify after plan")
    effects = {cat: [] for cat in set(ch_to_group.values())}
    for idx, (r, (ch, c)) in enumerate(zip(cls, chosen_seq)):
        assert r["ch"] == ch and r["stem"] == c["stem"], (
            f"classification out of sync with merged_channels at row {idx}; rerun classify")
        if ch in ch_to_group:
            effects[ch_to_group[ch]].append(
                {"ch": ch, "stem": c["stem"], "abs": c["abs"], "pool": c["pool"],
                 "dur": r["dur"], "idx": idx})
    return effects


def _emit_audio(entry, dst):
    # Ship every sound VERBATIM (byte-for-byte copy): no re-encode, no gain. The source's own
    # X-Ray ogg comment blob (version/min/max/base_volume) rides along untouched, so the engine
    # applies the SOURCE's attenuation and base volume at play - the pipeline preserves, it does
    # not compute. (The old ffmpeg volume path was removed because it re-baked a lossy gain AND
    # dropped that blob, dropping attenuation to the 1/300 engine default.) Loudness is only
    # MEASURED and flagged (cmd_loudness); it is never applied to the samples or to base_volume.
    dst.parent.mkdir(parents=True, exist_ok=True)
    import shutil as sh
    sh.copy2(entry["abs"], dst)


# --- n108: X-Ray ogg comment blob (per-file min/max distance + base_volume) ------------
# The engine reads the FIRST vorbis comment of an ogg as a binary struct (version 0x0003:
# u32 ver, f32 min, f32 max, f32 base_volume, u32 game_type, f32 max_ai) and applies
# base_volume plus the min/max attenuation at play (SoundRender_Source_loader.cpp:108-152,
# SoundRender_Emitter_FSM.cpp:133,361). A missing/text-tagged comment falls back to 1/300 +
# base_volume 1.0. ffmpeg CANNOT write it (it emits text tags), so we rewrite the comment
# header page directly - lossless: only page 1 changes, the audio pages are byte-identical.

def _crc_ogg(data):
    crc = 0
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04c11db7) & 0xffffffff if (crc & 0x80000000) else (crc << 1) & 0xffffffff
    return crc


def _ogg_pages(d):
    off, out = 0, []
    while off < len(d) and d[off:off + 4] == b"OggS":
        nseg = d[off + 26]
        segs = d[off + 27:off + 27 + nseg]
        dlen = sum(segs)
        out.append((off, bytes(segs), d[off + 27 + nseg:off + 27 + nseg + dlen]))
        off += 27 + nseg + dlen
    return out, off


def _ogg_packets(segs, body):
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
    for pk in packets:
        n = len(pk)
        while n >= 255:
            segtab.append(255); n -= 255
        segtab.append(n); body += pk
    if len(segtab) > 255:
        return None
    page = (b"OggS" + bytes([0, htype]) + struct.pack("<q", granule) +
            struct.pack("<I", serial) + struct.pack("<I", seq) +
            struct.pack("<I", 0) + bytes([len(segtab)]) + bytes(segtab) + body)
    return page[:22] + struct.pack("<I", _crc_ogg(page)) + page[26:]


def _write_blob(path, mn, mx, bv):
    """Write a 0x0003 X-Ray blob as comment[0], losslessly. Only the standard
    [ID | comment+setup | audio...] layout is handled; anything else is left unchanged
    (returns False). Audio pages are byte-identical after the write."""
    d = path.read_bytes()
    pg, end = _ogg_pages(d)
    if end != len(d) or len(pg) < 3:
        return False
    pkts = _ogg_packets(pg[1][1], pg[1][2])
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


def _audio_hash(path):
    """md5 of the audio pages (everything after the ID + comment/setup header pages), so a
    comment-blob rewrite still verifies as the same audio as its verbatim source."""
    pg, _ = _ogg_pages(path.read_bytes())
    return hashlib.md5(b"".join(p[2] for p in pg[2:])).hexdigest()


def _safe_audio_hash(path):
    """_audio_hash, or None on a malformed/unreadable ogg (never abort the scan for one bad file)."""
    try:
        return _audio_hash(path)
    except Exception:
        return None


def _slug(name):
    """Filesystem-safe lowercase slug of a source filename: letters, digits, underscore only."""
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "sound"


def _deployed_stem(entry):
    """The n124 deployed name (no extension): <source-name slug>_<audio hash>. Deterministic - depends
    only on the entry's own filename and audio, so every stage recomputes the same name with no shared
    counter, and the blob-agnostic audio hash means writing the ogg blob never changes it. The hash
    disambiguates two distinct sounds a pack shipped under one filename; identical audio collapses to one
    file. Replaces the positional N that re-indexed the whole tree whenever content was added or removed."""
    base = _slug(Path(entry["stem"]).name)
    h = (_safe_audio_hash(Path(entry["abs"])) or file_hash(entry["abs"]))[:10]
    return f"{base}_{h}"


# Config sources scanned for base ambient channels, so a removal exists for whatever channel any
# installed pack files one of our sounds under. An absent channel is safely ignored by DLTX
# (warn-and-discard, no CTD - Xr_ini.cpp:1383-1400).
VETO_CONFIG_ROOTS = [
    "D:/Games/GAMMA/GAMMA/mods",
    "C:/Users/damian/Downloads/anomaly_audio_mods",
    "D:/Games/GAMMA/Anomaly/tools/_unpacked",
]


def _sc_channel_sounds(sc_path):
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
            for t in code.split("=", 1)[1].split(","):
                t = t.strip()
                if t and "no_sound" not in t.lower():
                    ch[cur].append(t)
    return ch


def _veto_dltx(effects):
    """Build the static DLTX overlay that removes our own sounds from the base ambient channels, so the
    base never doubles the director's copy. For every channel across every scanned pack that lists a
    sound whose AUDIO is one of ours (audio-page hash, blob-agnostic), emit `![channel]` +
    `<sounds = <path>` - a per-item removal that leaves the channel's other sounds.

    Every channel we remove from also gets `>sounds = ambient\\no_sound`. A channel loaded as a
    System A bed CTDs on an empty `sounds` (Environment_misc.cpp:105-108); the target install's channel
    composition is unknown to a static overlay (a channel partial in a scanned pack can be fully ours in
    the install actually played), so the placeholder is unconditional - a full removal can never leave a
    bed empty on any install. no_sound is silent, so a partially-removed channel is only marginally diluted.
    Returns (overlay_text, removal_count, channel_count)."""
    want = set()
    for entries in effects.values():
        for e in entries:
            h = _safe_audio_hash(Path(e["abs"]))
            if h:
                want.add(h)
    hcache = {}

    def ah(f):
        k = str(f)
        if k not in hcache:
            hcache[k] = _safe_audio_hash(f)
        return hcache[k]

    removals = {}       # channel(lower) -> set of raw sound strings to remove
    contributing = {}   # pack folder (under a scanned root) -> how many of our sounds it played
    for root in VETO_CONFIG_ROOTS:
        rootp = Path(root)
        for sc in rootp.rglob("configs/environment/sound_channels.ltx"):
            rel = sc.relative_to(rootp).parts
            pack = rel[0] if rel and rel[0] not in ("configs", "gamedata") else rootp.name
            snd_root = sc.parents[2] / "sounds"
            for chan, entries in _sc_channel_sounds(sc).items():
                for raw in entries:
                    f = snd_root / (raw.replace("\\", "/") + ".ogg")
                    if f.is_file() and ah(f) in want:
                        removals.setdefault(chan, set()).add(raw)
                        contributing[pack] = contributing.get(pack, 0) + 1
    out = ["; GENERATED by tools/merge.py - do not edit. Static DLTX veto: removes AlifeSpooks' own",
           "; sounds from the base ambient channels so the base never doubles the director's copy.",
           "; Matched by audio identity (blob-agnostic) against every sound_channels.ltx under the roots below.",
           "; An absent channel is ignored by DLTX; every removed-from channel gets ambient\\no_sound.",
           ";",
           "; TESTED-AGAINST - scanned roots (VETO_CONFIG_ROOTS):"]
    for root in VETO_CONFIG_ROOTS:
        out.append(";   %s" % root)
    out.append("; Mods/packs that actually played one of our sounds and were vetoed (folder (count)):")
    for pack in sorted(contributing):
        out.append(";   %s (%d)" % (pack, contributing[pack]))
    out.append("")
    for chan in sorted(removals):
        out.append("![%s]" % chan)
        for raw in sorted(removals[chan]):
            out.append("<sounds = %s" % raw)
        out.append(">sounds = ambient\\no_sound")
        out.append("")
    return "\n".join(out), sum(len(v) for v in removals.values()), len(removals)


def _norm_bv(peak_db):
    """base_volume (linear) that lifts a file peaking at peak_db up to TARGET_PEAK_DB."""
    return round(10.0 ** ((TARGET_PEAK_DB - peak_db) / 20.0), 3)


def _normalize_blobs(effects, snd):
    """Write every kept file's ogg blob: its source min/max (per-category median for a blob-less file,
    so it attenuates like its mates instead of the 1/300 default) plus a base_volume that peak-normalizes
    it to TARGET_PEAK_DB. Lossless bitstream rewrite, no re-encode. Peak comes from _loudness_cull."""
    wrote = skipped = 0
    for cat in sorted(effects):
        names = [_deployed_stem(e) for e in effects[cat]]
        blobs = [_read_blob((snd / cat / f"{n}.ogg").read_bytes()) for n in names]
        carried = [b for b in blobs if b]
        cmin = _median(sorted(c[0] for c in carried)) if carried else 1.0
        cmax = _median(sorted(c[1] for c in carried)) if carried else 300.0
        if cmax <= cmin:
            cmax = cmin + 1.0
        for e, n, b in zip(effects[cat], names, blobs):
            mn, mx = (b[0], b[1]) if b else (cmin, cmax)
            if _write_blob(snd / cat / f"{n}.ogg", mn, mx, _norm_bv(e["peak"])):
                wrote += 1
            else:
                skipped += 1
    print(f"normalize: wrote base_volume+blob for {wrote} files (peak -> {TARGET_PEAK_DB} dB), "
          f"skipped {skipped} (non-standard ogg layout)")


# Each effect channel keeps its VERBATIM source settings - no median. Channels are grouped
# by (mood, exact-settings-tuple): one deployed channel as_eff_<mood>_<n> per distinct tuple,
# so a source channel's period/distance/indoor/height survive exactly (provenance-faithful).
# The mood is only a tag for the MCM knobs; as_director reads it off the <mood> in the name.
def _chan_settings(lines):
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


def effect_group_map():
    """category -> category identity, for every category that captured content. The deploy groups a
    sound into the directory named by its category (structural capture already assigned it)."""
    mc = json.loads((HERE / "merged_channels.json").read_text())
    return {cat: cat for cat in sorted(mc) if mc[cat]["chosen"]}


def _source_height_map():
    """source-stem -> the height its source channel placed it at, AGGREGATED across every pack: if the same
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
            for stem in cd["stems"]:                   # stems are already ext-less, forward-slash (parse_channels)
                hmap[stem] = h if stem not in hmap else max(hmap[stem], h)
    return hmap


def cmd_deploy(a):
    root = Path(a.root) if a.root else GDATA
    env = root / "configs/environment"
    snd = root / "sounds/zs"
    mc = json.loads((HERE / "merged_channels.json").read_text())
    cls = json.loads((HERE / "classification.json").read_text())
    ch_to_cat = effect_group_map()                 # source channel -> category
    effects = _build_layers(mc, cls, ch_to_cat)    # category -> [entries]
    _loudness_cull(effects)                        # measure peak, drop near-silent, store peak per file

    _clean(snd); _clean(env / "ambients")
    for stale in ("mod_sound_channels_alifespooks.ltx", "as_channel_layers.ltx"):
        (env / stale).unlink(missing_ok=True)      # old channel model, no longer written

    # Emit each sound into our OWN category directory: zs\<category>\N.ogg. There is no engine
    # sound_channels.ltx for our content - the director reads as_manifest, not channels.
    for cat in sorted(effects):
        for e in effects[cat]:
            _emit_audio(e, snd / cat / f"{_deployed_stem(e)}.ogg")

    _normalize_blobs(effects, snd)    # peak-normalize base_volume + write the attenuation blob per file

    # as_manifest: category -> its sounds, each { path, min_distance, max_distance, height }. The director
    # reads THIS instead of sound_channels.ltx. min/max come from the DEPLOYED ogg blob (n108), so the
    # director's positioning and the engine's attenuation use one curve. height is the sound's ORIGINAL
    # source-channel height, aggregated across every pack by _source_height_map (highest non-zero wins, so a
    # pack that flattened height to 0 never beats one that kept it); 0 only when no pack wired it. Anomaly Lua cannot list a
    # directory at runtime, so the sound list ships as data. Paths only - no play rules (env/requires/gates
    # live in as_director, not the manifest).
    man = ["--- as_manifest: GENERATED by tools/merge.py, do not edit. Category -> its sounds for the",
           "--- director (as_director reads this, not sound_channels.ltx). Each: { path, min, max, height }.",
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

    hmap = _source_height_map()                        # recover each sound's ORIGINAL source-channel height
    for cat in sorted(effects):
        cells = []
        for e in effects[cat]:
            n = _deployed_stem(e)
            b = _read_blob((snd / cat / f"{n}.ogg").read_bytes())
            mn, mx = (round(b[0], 1), round(b[1], 1)) if b else (1, 300)
            h = hmap.get(e["stem"], 0)                 # aggregated source height (any pack), else 0
            cells.append('{ "zs\\\\%s\\\\%s", %s, %s, %s }' % (cat, n, mn, mx, h))
        man.append('\t["%s"] = {' % cat)
        man += _pack(cells, "\t\t")
        man.append("\t},")
    man += ["}"]
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "as_manifest.script").write_text("\n".join(man) + "\n", encoding="utf-8")

    # Static DLTX veto overlay: remove our own sounds from the base ambient channels so the base never
    # doubles the director. Per-file removals across every scanned pack, matched by audio identity; bed
    # channels kept non-empty. Deterministic at config load - no runtime clone owns the muting.
    dltx, n_rm, n_ch = _veto_dltx(effects)
    env = root / "configs" / "environment"
    env.mkdir(parents=True, exist_ok=True)
    (env / "mod_sound_channels_alifespooks.ltx").write_text(dltx, encoding="utf-8")

    print(f"deployed to {root}")
    print(f"  categories: {len(effects)}; sounds: {sum(len(v) for v in effects.values())}")
    print(f"  veto DLTX: {n_rm} removals across {n_ch} channels")


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
    chosen = {}                                        # source hash -> (ch, stem)
    for ch, c in _iter_chosen(mc):
        chosen[file_hash(c["abs"])] = (ch, c["stem"])
    deployed = set()                                   # AUDIO hashes actually shipped - n108
    zs = GDATA / "sounds/zs"                            # rewrites comment headers, so a shipped
    for f in zs.rglob("*.ogg"):                         # file's BYTES differ from source while its
        deployed.add(_audio_hash(f))                    # audio does not; match blob-agnostic.
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
            h = file_hash(f)
            dark = any(k in low for k in DARK_KW)
            emission = any(k in low for k in EMISSION_KW)
            excluded = any(x in low for x in EXCLUDE)   # intentionally out-of-scope trees (ambience_exp, ...)
            under_root = low.split("/", 1)[0] in INCLUDE_ROOTS
            if _audio_hash(f) in deployed:
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
                        [c["abs"] for _ch, c in _iter_chosen(mc)], sp.DEF_JOBS)
    chosen_by_dur = collections.defaultdict(list)
    for fp, dur in chosen_fp:
        if fp:
            chosen_by_dur[dur].append(fp)

    def _fp(t):
        _n, _r, f = t
        return (sp.fingerprint(str(f), FP_LEN), round(float((sp.probe(str(f)) or {}).get("duration") or 0)))
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


def _channel_sections():
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
    ch_to_cat = effect_group_map()
    effects = _build_layers(mc, cls, ch_to_cat)
    _loudness_cull(effects)              # SAME drop deploy applies, so the N-numbering matches the tree
    zs = (Path(a.root) if getattr(a, "root", None) else GDATA) / "sounds/zs"   # honor --root like deploy

    # Structural capture: a sound's origin is its SOURCE PATH (orig_dir/orig_file from the stem) + the
    # pack it came from. No channel/settings/sections columns - categories are not channels. min/max/
    # base_volume live in the deployed ogg blob. The audio self-verify is the preservation proof.
    cols = ["deployed", "category", "orig_mod", "orig_dir", "orig_file", "base_volume"]
    rows, verify_ok, verify_bad = [], 0, 0
    for cat in sorted(effects):                       # every sound deploys to zs\<category>\<name>
        for e in effects[cat]:
            n = _deployed_stem(e)
            dep = f"zs\\{cat}\\{n}"
            stem = e["stem"]
            dfile = zs / cat / f"{n}.ogg"
            bv = ""
            if dfile.exists():
                b = _read_blob(dfile.read_bytes())
                if b:
                    bv = round(b[2], 3)
                if _audio_hash(dfile) == _audio_hash(Path(e["abs"])):
                    verify_ok += 1
                else:
                    verify_bad += 1
            rows.append([dep, cat, e["pool"], str(Path(stem).parent).replace("\\", "/"),
                         Path(stem).name, str(bv)])
    lines = ["\t".join(cols)] + ["\t".join(str(x) for x in r) for r in rows]
    (HERE / "provenance.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"provenance: {len(rows)} shipped sounds -> provenance.tsv")
    print(f"audio self-verify vs source (comment-blob-agnostic): {verify_ok} match, {verify_bad} MISMATCH")
    if verify_bad:
        print("  MISMATCH != 0 -> the deploy ordering does NOT reproduce the tree; provenance is NOT exact.")


def cmd_all(a):
    """Run the whole pipeline in order: plan -> classify -> loudness -> deploy -> ledger -> provenance.
    One command so the sequence (and the classify-after-plan rule) can never be got wrong by hand."""
    import types, time
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
    sub.add_parser("ledger").set_defaults(func=cmd_ledger)
    sub.add_parser("provenance").set_defaults(func=cmd_provenance)
    p = sub.add_parser("all"); p.add_argument("--root"); p.set_defaults(func=cmd_all)
    a = ap.parse_args(); a.func(a)
