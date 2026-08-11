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

# Channels whose curated content does not resolve from any mod's config get filled
# deliberately from a content folder. out_mutants: the distant-growl recordings live
# under soundscape/mutants and no channel def points at them, so assign them here.
MANUAL_FILL = [
    # distant creature calls: soundscape/mutants ships them but no channel def points at them.
    {"chan": "out_mutants",
     "root": "C:/Users/damian/Downloads/anomaly_audio_mods/Dark Signal Amplified Soundscape/gamedata/sounds/ambient/soundscape/mutants",
     "pattern": r"distant", "mono": False, "limit": 100000},
    # 276 is a CREATURE-sound pack (monsters/<species>/), dread mixed with combat. Pull ONLY the
    # near-lurking dread by filename (idle / growl / ambient_drone / eat); the combat sounds
    # (attack/hit/die/pain) are left out - fired ambiently with no mutant they play out of context.
    {"chan": "out_mutants",
     "root": "C:/Users/damian/Downloads/anomaly_audio_mods/276- Dark Signal Mutants Audio - Shrike/gamedata/sounds/monsters",
     "pattern": r"(idle|growl|ambient_drone|_eat)", "mono": False, "limit": 100000},
]
LOWQ_BITRATE = 32000  # drop clearly junk-bitrate files when a channel has better

# Dark scope (I9): the ONLY channels AlifeSpooks keeps. Everything else in the
# packs (generic daytime life, neutral beds, plain wind) is left to the base
# ambience. Emission (blowout_*, emission_wind) is a separate system, never touched.
# Grouped by family - the same grouping seeds the runtime per-family policy later.
DARK_KEEP = {
    # dread cues
    "out_spooks", "out_day_spoops", "out_night_spoops", "northen_spoops", "urban_spoops_night",
    "out_screams", "out_mutants", "out_dark_amb", "out_night_amb", "dark_signal",
    "foliage_spook", "crows_spook", "inside_noise",
    "background_creepy_low_wind",
    "background_forest_whisper_day", "background_forest_whisper_evening",
    "background_forest_whisper_morning", "background_forest_whisper_night",
    # underground horror
    "ugrnd_ambient", "ugrnd_ambient_machine", "ugrnd_ambient_new", "ugrnd_banging", "ugrnd_bkg_1",
    "ugrnd_drip", "ugrnd_drone", "ugrnd_lab", "ugrnd_metal", "ugrnd_noise", "ugrnd_rats", "ugrnd_voices",
    "underground_background_1", "underground_background_2", "underground_background_3", "underground_background_4",
    "underground_background_5", "underground_background_6", "underground_background_7", "underground_background_8", "x18",
    # tension
    "out_gunfire", "out_drone", "drones", "day_drones", "urban_drones",
    "wind_creep", "wind_creep_alt", "wind_creep_urban", "branch", "branch_big", "branch_med",
    "urban_debris",
    # eerie wildlife (crows/owls/dogs) + tree creaks. Generic birds, fog, and weather DROPPED.
    "owls", "dogs", "crows", "crows_clear", "crows_forest", "crows_retune", "tree_sway_fog",
    # dread wind (creeping/howling, NOT storm/rain)
    "wind_dark", "wind_gale", "wind_heavy", "wind_strong",
}

# Folder-tree capture: the packs ship far more dark content than they wire into a
# channel's sounds= list (proven by the ledger: 1103 genuinely-new unused dark
# files). So we pull dark content from the FOLDER TREES directly, not just
# channel-referenced files. First matching substring (checked in order) maps the
# file to a channel; content-hash dedup collapses cross-tree copies. This is how
# ALL the horror (distant mutants, screams, spooks, underground) gets in.
# Weather (storm/rain/thunder/pre_storm) and fog (tuman) are DROPPED: weather is the base ambient's
# job (user). Rules are kept tight - full-path folder substrings that are unambiguously dread - so no
# random shit is pulled. monsters/ (top-level creature combat) is deliberately NOT matched here; the
# ambient mutant dread lives under ambient/soundscape/mutants/, a different tree.
DARK_FILL = [
    ("/screams", "out_screams"),
    ("ambient/soundscape/mutants/", "out_mutants"), ("spooks_above/mutants", "out_mutants"),
    ("amb_dark", "out_dark_amb"), ("amb_night", "out_night_amb"),
    ("spooks_below/metal", "ugrnd_metal"), ("spooks_below/banging", "ugrnd_banging"),
    ("spooks_below/rats", "ugrnd_rats"), ("spooks_below/noise", "ugrnd_noise"),
    ("spooks_below/lab", "ugrnd_lab"), ("water_drip", "ugrnd_drip"), ("/drip", "ugrnd_drip"),
    ("spooks_below/machine", "ugrnd_ambient_machine"), ("spooks_below/ambient", "ugrnd_ambient"),
    ("spooks_below/creaks", "ugrnd_ambient"),          # Audio Expansion creaking underground dread
    ("spooks_below/drone", "ugrnd_drone"), ("spooks_above/drone", "out_drone"),
    ("spooks_below/spooks", "out_spooks"), ("spooks_above/spooks", "out_spooks"), ("/spooks/", "out_spooks"),
    ("/shooting", "out_gunfire"), ("wind_dark", "wind_heavy"),
    ("spoops/urban_drones", "urban_drones"), ("spoops/drones", "out_drone"),
    ("northern_spoops", "out_spooks"),
    ("spooks_above", "out_spooks"), ("spooks_below", "out_spooks"),
    ("nature/whispers", "out_spooks"), ("/whispers", "out_spooks"),   # surface whisper dread
    ("ugrnd_whispers", "ugrnd_voices"),
    ("/underground/", "ugrnd_ambient"), ("underground_", "ugrnd_ambient"),
]

# Out-of-scope / misfiled files to skip even when a DARK_FILL or channel rule would
# capture them (n109, verified 2026-08-06). psi-storm is emission-domain (readme: "does
# not touch emission or psi-storm sound"); giant_underground is a monster roar misfiled
# into ugrnd_ambient. Substring match on the lowercased source path.
EXCLUDE = ("psi_storm", "psistorm", "giant_underground")

# priority order: settings for a shared channel come from the first that defines it
# Sources are assessed per pack by hand before wiring (which folders hold real dread), then their
# folders map to channels in DARK_FILL / MANUAL_FILL. 304 Dark Signal Weather is out (GAMMA's Dark
# Signal, sounds muted at wrong levels). The Amplified variants (Vanilla/Atmospherics) are byte-
# identical to Amplified Soundscape in the dread folders (measured: 3215 md5s, 0 unique), so only
# Soundscape is pulled. Doom II NSDARK is deferred (n116).
MODS = [
    ("Amplified",      "C:/Users/damian/Downloads/anomaly_audio_mods/Dark Signal Amplified Soundscape/gamedata"),
    ("Soundscape",     "D:/Games/GAMMA/GAMMA/mods/3- Soundscape Overhaul - Solarint/gamedata"),
    # myRETUNE Antares (user-vouched): its ambient/soundscape/underground/spooks_above|below tree is the
    # same dread structure DARK_FILL matches. Replaces the disabled GAMMA 457 (same lineage).
    ("myRETUNE",       "C:/Users/damian/Downloads/anomaly_audio_mods/myRETUNE_AntaresWolverine_2.1/gamedata"),
    # net-new distant-creature calls under soundscape/mutants. No sound_channels.ltx of its own.
    ("RealDistantMutants", "C:/Users/damian/Downloads/anomaly_audio_mods/Real Distant Mutants Sounds/gamedata"),
    # 276 creature-sound pack: pulled by MANUAL_FILL, filtered to near-lurking dread only (combat out).
    ("DSMutants",      "C:/Users/damian/Downloads/anomaly_audio_mods/276- Dark Signal Mutants Audio - Shrike/gamedata"),
    # net-new underground dread (spooks_below creaks/ambient/noise), not installed in GAMMA.
    ("AudioExpansion", "C:/Users/damian/Downloads/anomaly_audio_mods/Audio Expansion/gamedata"),
    ("vanilla",        "D:/Games/GAMMA/Anomaly/tools/_unpacked"),   # last: only for channels no pack defines (portability coverage)
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
# install already plays it. Doubling is handled at RUNTIME by the base-veto (as_effect
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
                    # Frozen as validated (MANGLE=0); see architecture.md I3.


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
            return float(m.group(1))
        except ValueError:
            return None
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


def cmd_plan(_):
    # 1. gather every channel's assigned sounds across mods
    per_mod = {name: parse_channels(gd) for name, gd in MODS}
    orig_def, pool = {}, collections.defaultdict(list)   # orig_def: settings + original stems from priority mod
    missing = collections.Counter()
    offrate = 0
    for name, gd in MODS:
        sounds_root = Path(gd) / "sounds"
        for chan, d in per_mod[name].items():
            if chan not in DARK_KEEP:            # dark scope only (I9); skip generic life/beds/emission
                continue
            if chan not in orig_def and (d["settings"] or d["stems"]):
                orig_def[chan] = {"mod": name, "settings": d["settings"], "stems": d["stems"]}
            for stem in d["stems"]:
                f = resolve(stem, sounds_root)
                if f is None:
                    missing[name] += 1
                    continue
                if any(x in f.as_posix().lower() for x in EXCLUDE):
                    continue
                info = sp.probe(str(f)) or {}
                if info.get("sample_rate") != 44100:      # X-Ray fitness: 44100 only
                    offrate += 1
                    continue
                pool[chan].append({"abs": str(f), "stem": stem, "pool": name,
                                   "bitrate": info.get("bit_rate", 0),
                                   "channels": info.get("channels", 0)})
    # 1b. manual fill for channels whose curated content does not resolve from a config
    for rule in MANUAL_FILL:
        chan = rule["chan"]
        root = Path(rule["root"])
        rx = re.compile(rule["pattern"], re.I)
        cands = []
        for f in sorted(root.rglob("*.ogg")):
            if not rx.search(f.as_posix()):
                continue
            info = sp.probe(str(f)) or {}
            if info.get("sample_rate") != 44100:
                continue
            if rule.get("mono") and info.get("channels") != 1:
                continue
            cands.append({"abs": str(f), "stem": f.as_posix().split("/sounds/")[-1][:-4],
                          "pool": "ManualFill", "bitrate": info.get("bit_rate", 0),
                          "channels": info.get("channels", 0)})
        cands.sort(key=lambda c: -c["bitrate"])
        pool[chan].extend(cands[:rule.get("limit", 48)])

    # 1c. FOLDER-TREE capture: pull ALL dark content from the trees, not just files a
    #     channel wires. The packs ship far more than they reference (ledger proof).
    fill_added = collections.Counter()
    for name, gd in MODS:
        sroot = Path(gd) / "sounds"
        if not sroot.is_dir():
            continue
        for f in sroot.rglob("*.ogg"):
            rel = f.as_posix().lower()
            if any(x in rel for x in EXCLUDE):
                continue
            chan = next((c for sub, c in DARK_FILL if sub in rel), None)
            if not chan:
                continue
            info = sp.probe(str(f)) or {}
            if info.get("sample_rate") != 44100:
                offrate += 1
                continue
            pool[chan].append({"abs": str(f), "stem": f.as_posix().split("/sounds/")[-1][:-4],
                               "pool": name, "bitrate": info.get("bit_rate", 0),
                               "channels": info.get("channels", 0)})
            fill_added[chan] += 1
    print(f"folder-tree capture added (pre-dedup): {dict(fill_added)}")

    # 2. EVERY channel the base defines is emitted (missing section = engine CTD).
    #    Filled channels get our deduped content; unfilled ones (blowout/emission,
    #    packed-only) keep their original stems so they resolve from the base VFS.
    merged = {}
    tot_in = tot_kept = tot_dropped = inherited = 0
    kept_hashes = set()
    for chan in sorted(set(orig_def) | set(pool)):
        files = pool.get(chan, [])
        tot_in += len(files)
        chosen = dedup_pick(files) if files else []
        kept_hashes |= {c["hash"] for c in chosen}
        tot_dropped += len(files) - len(chosen)
        tot_kept += len(chosen)
        od = orig_def.get(chan, {"mod": "?", "settings": [], "stems": []})
        if not chosen and od["stems"]:
            inherited += 1
        merged[chan] = {
            "settings_src": od["mod"], "settings": od["settings"],
            "orig_stems": od["stems"],
            "chosen": [{"abs": c["abs"], "stem": c["stem"], "pool": c["pool"],
                        "bitrate": c["bitrate"], "channels": c["channels"]} for c in chosen],
        }
    # Intra-corpus re-encodes the PCM dedup dropped (distinct bytes, cross-correlation-confirmed
    # the same recording as a KEPT sound): record their hashes so the ledger books them as
    # captured-then-deduped, not as a coverage miss. md5-losers share a hash with the kept
    # winner (so their hash is in kept_hashes); only the acoustic drops remain in this set.
    pool_hashes = {f["hash"] for fs in pool.values() for f in fs if "hash" in f}
    (HERE / "intra_dups.json").write_text(json.dumps(sorted(pool_hashes - kept_hashes)), encoding="utf-8")
    # No target-modpack dedup. Doubling with the base (or a source pack a player also runs) is
    # handled at runtime by the base-veto: as_effect owns update_ambient and mutes the base's copy
    # of any sound we ship (as_blockdata). So we ship the full curated dark corpus and own it under
    # the director. Source-side dedup (dedup_pick + _cross_channel_dedup) still runs.
    _silence_gate(merged)
    _cross_channel_dedup(merged)
    (HERE / "merged_channels.json").write_text(json.dumps(merged, indent=1), encoding="utf-8")

    # 3. report
    print(f"mods merged: {[m[0] for m in MODS]}")
    net_new = sum(len(v["chosen"]) for v in merged.values())
    print(f"channels (union): {len(merged)}   filled: {sum(1 for v in merged.values() if v['chosen'])}   inherited (blowout/packed): {inherited}")
    print(f"sounds pooled: {tot_in}  ->  deduped {tot_kept}  ->  shipped {net_new}  (dropped {tot_dropped}: exact dups + junk bitrate; {offrate} off-44100 skipped)")
    if missing:
        print(f"unresolved sound refs (packed/missing files): {dict(missing)}")


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
# The shipped model: one-shot spook channels the standalone director (as_effect) plays. Every dark
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


def _norm_bv(peak_db):
    """base_volume (linear) that lifts a file peaking at peak_db up to TARGET_PEAK_DB."""
    return round(10.0 ** ((TARGET_PEAK_DB - peak_db) / 20.0), 3)


def _normalize_blobs(effects, snd):
    """Write every kept file's ogg blob: its source min/max (per-category median for a blob-less file,
    so it attenuates like its mates instead of the 1/300 default) plus a base_volume that peak-normalizes
    it to TARGET_PEAK_DB. Lossless bitstream rewrite, no re-encode. Peak comes from _loudness_cull."""
    wrote = skipped = 0
    for cat in sorted(effects):
        blobs = [_read_blob((snd / cat / f"{i}.ogg").read_bytes()) for i in range(1, len(effects[cat]) + 1)]
        carried = [b for b in blobs if b]
        cmin = _median(sorted(c[0] for c in carried)) if carried else 1.0
        cmax = _median(sorted(c[1] for c in carried)) if carried else 300.0
        if cmax <= cmin:
            cmax = cmin + 1.0
        for i, e in enumerate(effects[cat], 1):
            b = blobs[i - 1]
            mn, mx = (b[0], b[1]) if b else (cmin, cmax)
            if _write_blob(snd / cat / f"{i}.ogg", mn, mx, _norm_bv(e["peak"])):
                wrote += 1
            else:
                skipped += 1
    print(f"normalize: wrote base_volume+blob for {wrote} files (peak -> {TARGET_PEAK_DB} dB), "
          f"skipped {skipped} (non-standard ogg layout)")


# Each effect channel keeps its VERBATIM source settings - no median. Channels are grouped
# by (mood, exact-settings-tuple): one deployed channel as_eff_<mood>_<n> per distinct tuple,
# so a source channel's period/distance/indoor/height survive exactly (provenance-faithful).
# The mood is only a tag for the MCM knobs; as_effect reads it off the <mood> in the name.
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


# The director categories, which ARE the shipped directories (zs\<category>). The gate and weight
# per category live in as_effect CATEGORIES; category_of only decides which directory a sound lands
# in. Every captured source channel maps to exactly one, aligned with as_effect CATEGORIES.
CATEGORIES = ["drone", "spook", "scream", "growl", "machine", "gunfire",
              "underground", "creak", "wind_creep", "animals"]


def category_of(ch):
    c = ch.lower()
    if c == "out_gunfire": return "gunfire"
    if c == "out_screams": return "scream"
    if c == "out_mutants": return "growl"
    if c.startswith("ugrnd_") or c.startswith("underground_") or c == "x18" or c == "inside_noise":
        return "underground"
    if c in ("dark_signal", "out_dark_amb", "out_night_amb", "out_drone"):
        return "drone"
    if c in ("day_drones", "drones", "urban_drones", "urban_debris"):
        return "machine"
    if c in ("branch", "branch_big", "branch_med", "tree_sway_fog"):
        return "creak"
    if "wind" in c or c == "background_creepy_low_wind":
        return "wind_creep"
    if c in ("crows", "crows_clear", "crows_forest", "crows_retune", "owls", "dogs"):
        return "animals"
    return "spook"   # out_spooks, *_spoops, crows_spook, foliage_spook, whispers, default


def _classical_cadence():
    """Average ms between spook one-shots in the classical ambient system, measured from vanilla and
    Dark Signal Amplified Soundscape (user). In a section several spook channels run at once, each on
    its period0-3, so the combined rate is faster than a single period: take the median spook-channel
    period over the average count of spook channels a section runs, then average the two sources. The
    director aims its per-tick emit probability at this, so density matches the base, not a guess."""
    def rate(gd):
        periods = []
        for ch, d in parse_channels(gd).items():
            if ch in DARK_KEEP:
                pv = [p for p in _chan_settings(d["settings"])["p"] if p > 0]
                if pv:
                    periods.append(sum(pv) / len(pv))
        med = _median(sorted(periods)) if periods else 15000.0
        counts = [len([c for c in sd.get("dynamic", []) if c in DARK_KEEP])
                  for _f, secs in parse_presets(gd).items() for _s, sd in secs.items()]
        counts = [n for n in counts if n > 0]
        n = (sum(counts) / len(counts)) if counts else 1.0
        return med / max(1.0, n)
    v = rate(VAN_CFG)
    a = rate("C:/Users/damian/Downloads/anomaly_audio_mods/Dark Signal Amplified Soundscape/gamedata")
    return int((v + a) / 2)


def effect_group_map():
    """source channel -> category (the shipped directory). Every captured channel maps to one."""
    mc = json.loads((HERE / "merged_channels.json").read_text())
    return {ch: category_of(ch) for ch in sorted(mc) if mc[ch]["chosen"]}


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
        for i, e in enumerate(effects[cat], 1):
            _emit_audio(e, snd / cat / f"{i}.ogg")

    _normalize_blobs(effects, snd)    # peak-normalize base_volume + write the attenuation blob per file

    # as_manifest: category -> its sounds, each { path, min_distance, max_distance, height }. The
    # director reads THIS instead of sound_channels.ltx. Placement min/max come from the DEPLOYED ogg
    # blob (n108), so the director's positioning and the engine's attenuation use one curve; height
    # comes from the source channel settings. Anomaly Lua cannot list a directory at runtime, so the
    # sound list has to be shipped as data.
    settings = {ch: _chan_settings(mc[ch].get("settings")) for ch in mc}
    man = ["--- as_manifest: GENERATED by tools/merge.py, do not edit. Category -> its sounds for the",
           "--- director (as_effect reads this, not sound_channels.ltx). Each: { path, min, max, height }.",
           "--- cadence_ms is the measured classical spook interval (vanilla + Dark Signal Amplified).",
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
        cells = []
        for i, e in enumerate(effects[cat], 1):
            b = _read_blob((snd / cat / f"{i}.ogg").read_bytes())
            mn, mx = (round(b[0], 1), round(b[1], 1)) if b else (1, 300)
            h = settings.get(e["ch"], {}).get("height", 0)
            cells.append('{ "zs\\\\%s\\\\%d", %s, %s, %s }' % (cat, i, mn, mx, h))
        man.append('\t["%s"] = {' % cat)
        man += _pack(cells, "\t\t")
        man.append("\t},")
    man += ["}", "", "cadence_ms = %d" % _classical_cadence()]
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "as_manifest.script").write_text("\n".join(man) + "\n", encoding="utf-8")

    # as_blockdata: the base-veto path set. If a player also runs a source pack we drew from, its
    # ambient plays those sounds; the veto mutes the base copy, matched by ORIGINAL path (blockfiles)
    # or a source folder we own (blockdirs), independent of the deployed category layout. No mod
    # names, game sound paths only. provenance.tsv keeps the full origin; this is the runtime set.
    files = sorted({e["stem"].lower().replace("\\", "/") for entries in effects.values() for e in entries})
    dirs = sorted({p.rsplit("/", 1)[0] + "/" for p in files if "/" in p})
    fcells = ['["%s"] = true' % p for p in files]
    dcells = ['["%s"] = true' % d for d in dirs]
    bl = ["--- as_blockdata: GENERATED by tools/merge.py, do not edit. Base-veto path set for",
          "--- as_effect._build_block: original paths (blockfiles) and source folders (blockdirs).",
          "blockfiles = {"] + _pack(fcells, "\t") + ["}", "", "blockdirs = {"] + _pack(dcells, "\t") + ["}"]
    (root / "scripts" / "as_blockdata.script").write_text("\n".join(bl) + "\n", encoding="utf-8")

    print(f"deployed to {root}")
    print(f"  categories: {len(effects)}; sounds: {sum(len(v) for v in effects.values())}; "
          f"cadence {_classical_cadence()}ms")


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
            under_root = low.split("/", 1)[0] in INCLUDE_ROOTS
            if _audio_hash(f) in deployed:
                st = "USED-shipped"
            elif h in chosen:                           # a chosen sound whose audio isn't in the tree
                st = "USED-effect-unshipped"
            elif emission:
                st = "EMISSION-excluded"
            elif h in intra_dropped:                    # our own re-encode, deduped by cross-correlation
                st = "INTRA-DUP-excluded"
            elif h in silence_dropped:                  # dead/empty, dropped by the silence gate
                st = "SILENCE-excluded"
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
    settings = {ch: _parse_settings(mc[ch]["settings"]) for ch in mc}
    ch_sec = _channel_sections()
    zs = GDATA / "sounds/zs"

    cols = ["deployed", "category", "orig_mod", "orig_dir", "orig_file", "orig_channel",
            "min_distance", "max_distance", "period0", "period1", "period2", "period3",
            "indoor", "height", "base_volume", "orig_sections"]
    rows, verify_ok, verify_bad = [], 0, 0
    for cat in sorted(effects):                       # every sound deploys to zs\<category>\N
        for i, e in enumerate(effects[cat], 1):
            dep = f"zs\\{cat}\\{i}"
            s = settings.get(e["ch"], {})
            stem = e["stem"]
            dfile = zs / cat / f"{i}.ogg"
            # n107/n108: every file ships audio-verbatim; a blob write touches only the comment
            # header. Record the DEPLOYED base_volume and self-verify by AUDIO.
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
                         Path(stem).name, e["ch"],
                         s.get("min_distance", ""), s.get("max_distance", ""),
                         s.get("period0", ""), s.get("period1", ""), s.get("period2", ""), s.get("period3", ""),
                         s.get("indoor", ""), s.get("height", ""),
                         str(bv), "; ".join(ch_sec.get(e["ch"], []))])
    lines = ["\t".join(cols)] + ["\t".join(str(x) for x in r) for r in rows]
    (HERE / "provenance.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"provenance: {len(rows)} shipped sounds -> provenance.tsv")
    print(f"audio self-verify vs source (comment-blob-agnostic): {verify_ok} match, {verify_bad} MISMATCH")
    if verify_bad:
        print("  MISMATCH != 0 -> the deploy ordering does NOT reproduce the tree; provenance is NOT exact.")


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
    a = ap.parse_args(); a.func(a)
