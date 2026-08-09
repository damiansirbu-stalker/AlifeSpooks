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
MANUAL_FILL = {
    "out_mutants": {
        "root": "C:/Users/damian/Downloads/extra_mods_analysys/Dark Signal Amplified Soundscape/gamedata/sounds/ambient/soundscape/mutants",
        "pattern": "distant", "mono": False, "limit": 100000,   # no cap: capture every distant-creature call
    },
}
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
    "background_forest_whisper_morning", "background_forest_whisper_night", "background_forest_whisper_tuman",
    # underground horror
    "ugrnd_ambient", "ugrnd_ambient_machine", "ugrnd_ambient_new", "ugrnd_banging", "ugrnd_bkg_1",
    "ugrnd_drip", "ugrnd_drone", "ugrnd_lab", "ugrnd_metal", "ugrnd_noise", "ugrnd_rats", "ugrnd_voices",
    "underground_background_1", "underground_background_2", "underground_background_3", "underground_background_4",
    "underground_background_5", "underground_background_6", "underground_background_7", "underground_background_8", "x18",
    # tension
    "out_gunfire", "out_drone", "drones", "day_drones", "urban_drones",
    "wind_creep", "wind_creep_alt", "wind_creep_urban", "branch", "branch_big", "branch_med",
    "urban_debris",
    # eerie atmosphere (owls/dogs/crows/fog - confirmed in scope)
    "owls", "dogs", "crows", "crows_clear", "crows_forest", "crows_retune", "tree_sway_fog", "birds_night",
    "background_tuman_field_open", "background_tuman_field_openalt", "background_tuman_open",
    "background_tuman_open_alt", "background_tuman_open_alt2", "background_tuman_open_urban",
    # oppressive weather
    "storm", "storm_foliage", "storm_urban", "pre_storm", "background_storm_forest", "background_rain_forest",
    "background_wind_storm", "wind_dark", "wind_gale", "wind_heavy", "wind_strong",
    "rain_gust", "rain_urban_gust",
}

# Folder-tree capture: the packs ship far more dark content than they wire into a
# channel's sounds= list (proven by the ledger: 1103 genuinely-new unused dark
# files). So we pull dark content from the FOLDER TREES directly, not just
# channel-referenced files. First matching substring (checked in order) maps the
# file to a channel; content-hash dedup collapses cross-tree copies. This is how
# ALL the horror (distant mutants, screams, spooks, underground) gets in.
DARK_FILL = [
    ("/screams", "out_screams"),
    ("/mutants/", "out_mutants"), ("spooks_above/mutants", "out_mutants"),
    ("amb_dark", "out_dark_amb"), ("amb_night", "out_night_amb"),
    ("spooks_below/metal", "ugrnd_metal"), ("spooks_below/banging", "ugrnd_banging"),
    ("spooks_below/rats", "ugrnd_rats"), ("spooks_below/noise", "ugrnd_noise"),
    ("spooks_below/lab", "ugrnd_lab"), ("water_drip", "ugrnd_drip"), ("/drip", "ugrnd_drip"),
    ("spooks_below/machine", "ugrnd_ambient_machine"), ("spooks_below/ambient", "ugrnd_ambient"),
    ("spooks_below/creaks", "ugrnd_ambient"),          # Audio Expansion creaking underground dread

    ("spooks_below/drone", "ugrnd_drone"), ("spooks_above/drone", "out_drone"),
    ("spooks_below/spooks", "out_spooks"), ("spooks_above/spooks", "out_spooks"), ("/spooks/", "out_spooks"),
    ("/thunder", "storm"), ("/rain", "rain_gust"),
    ("/shooting", "out_gunfire"), ("wind_dark", "wind_heavy"),
    ("spoops/urban_drones", "urban_drones"), ("spoops/drones", "out_drone"), ("/drones", "out_drone"),
    ("northern_spoops", "out_spooks"), ("storm_debris", "storm"), ("wind_tuman", "background_tuman_open"),
    ("spooks_above", "out_spooks"), ("spooks_below", "out_spooks"), ("/underground/", "ugrnd_ambient"),
    ("thunder", "storm"), ("pre_storm", "pre_storm"), ("storm_", "storm"), ("rain_storm", "storm"),
    ("nature/whispers", "out_spooks"), ("/whispers", "out_spooks"),   # AudioExpansion surface whisper dread
    ("_storm", "storm"), ("stormstrike", "storm"),                    # *_storm beds + storm-strike one-shots
    ("ugrnd_whispers", "ugrnd_voices"),                              # dead in Audio Expansion; capture so the silence gate books them
    ("tuman", "background_tuman_open"), ("underground_", "ugrnd_ambient"),
]

# Out-of-scope / misfiled files to skip even when a DARK_FILL or channel rule would
# capture them (n109, verified 2026-08-06). psi-storm is emission-domain (readme: "does
# not touch emission or psi-storm sound"); giant_underground is a monster roar misfiled
# into ugrnd_ambient. Substring match on the lowercased source path.
EXCLUDE = ("psi_storm", "psistorm", "giant_underground")

# priority order: settings for a shared channel come from the first that defines it
MODS = [
    ("DarkSigWeather", "D:/Games/GAMMA/GAMMA/mods/304- Dark Signal Weather and Ambiance Audio - Shrike/gamedata"),
    ("Soundscape",     "D:/Games/GAMMA/GAMMA/mods/3- Soundscape Overhaul - Solarint/gamedata"),
    ("RETUNE",         "D:/Games/GAMMA/GAMMA/mods/457- RETUNE Ambiant Sounds - Aphrodite_child/gamedata"),
    ("Amplified",      "C:/Users/damian/Downloads/extra_mods_analysys/Dark Signal Amplified Soundscape/gamedata"),
    # net-new distant-creature calls (99 files, 0 content-hash overlap with Amplified's
    # mutant pool). No sound_channels.ltx of its own - captured via DARK_FILL /mutants/.
    ("RealDistantMutants", "C:/Users/damian/Downloads/anomaly_audio_mods/Real Distant Mutants Sounds/gamedata"),
    # net-new underground dread (spooks_below creaks/ambient/noise): 244 of 268 unique vs
    # active GAMMA + our corpus (measured 2026-08-06, fpcalc). Not installed in GAMMA.
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


def _dedup_entries(entries):
    """Waveform-dedup a REGROUPED deployed unit, keeping the first of each confirmed group
    (callers pre-sort by preference). dedup_pick works per SOURCE channel, but a loop bed
    pools many source channels, so a re-encode captured into two of them reappears in the bed.
    Same three-stage identity as dedup_pick (md5 -> fp -> PCM xcorr, complete-linkage) so the
    bed never loops the same recording; distinct variety is preserved."""
    if len(entries) <= 1:
        return list(entries)
    seen, reps = set(), []
    for e in entries:                                  # md5, keep first occurrence
        h = file_hash(e["abs"])
        if h not in seen:
            seen.add(h)
            reps.append(e)
    if len(reps) <= 1:
        return reps
    fpm = dict(zip((id(e) for e in reps),
                   sp.pmap(lambda e: sp.fingerprint(e["abs"], FP_LEN), reps, sp.DEF_JOBS)))
    durm = dict(zip((id(e) for e in reps),
                    sp.pmap(lambda e: round(float((sp.probe(e["abs"]) or {}).get("duration") or 0)),
                            reps, sp.DEF_JOBS)))
    clusters = []
    for e in reps:
        for cl in clusters:
            h = cl[0]
            if (fpm[id(e)] and fpm[id(h)] and abs(durm[id(e)] - durm[id(h)]) <= 1
                    and sp.fp_similarity(fpm[id(e)], fpm[id(h)]) >= BASE_SIM):
                cl.append(e)
                break
        else:
            clusters.append([e])
    keep = set()
    for cl in clusters:
        if len(cl) == 1:
            keep.add(id(cl[0]))
            continue
        pcmm = dict(zip((id(e) for e in cl),
                        sp.pmap(lambda e: sp.decode_pcm(e["abs"]), cl, sp.DEF_JOBS)))
        groups = []
        for e in cl:
            for g in groups:
                if all(sp.pcm_correlation(pcmm[id(e)], pcmm[id(m)]) >= DEDUP_XCORR for m in g):
                    g.append(e)
                    break
            else:
                groups.append([e])
        for g in groups:
            keep.add(id(g[0]))
    return [e for e in reps if id(e) in keep]


# --- base-dedup: never ship a sound the install already PLAYS ----------------
# The install plays a fixed set, winner-resolved: vanilla's own ambient channels
# (unpacked sounds_ambient.db0) + the GAMMA winner (DSW) active channels. Our content
# must exclude those by md5 AND by acoustic fingerprint - the packs re-encode the same
# sound to new bytes, so md5 alone misses the re-encoded copies (measured: ~250 of the
# "net-new" set were acoustic duplicates of a base-played sound). fpcalc + fp_similarity
# is the same same-sound test soundpool uses; BASE_SIM matches its dup_similarity_threshold.
VAN_CFG = "D:/Games/GAMMA/Anomaly/tools/_unpacked"
VAN_SND = Path("D:/Games/GAMMA/Anomaly/tmp_van_ambient/sounds")     # unpacked sounds_ambient.db0
CONVERTER = "D:/Games/GAMMA/Anomaly/tools/converter.exe"
VAN_DB = "D:/Games/GAMMA/Anomaly/db/sounds/sounds_ambient.db0"
GAMMA_WINNER = "D:/Games/GAMMA/GAMMA/mods/304- Dark Signal Weather and Ambiance Audio - Shrike/gamedata"
GAMMA_DEFINERS = [GAMMA_WINNER,
    "D:/Games/GAMMA/GAMMA/mods/3- Soundscape Overhaul - Solarint/gamedata",
    "D:/Games/GAMMA/GAMMA/mods/457- RETUNE Ambiant Sounds - Aphrodite_child/gamedata"]
FP_LEN = 30
BASE_SIM = 0.88     # Chromaprint recall threshold: >= this makes a pair a same-sound CANDIDATE
DEDUP_XCORR = 0.90  # PCM cross-correlation DECIDER: >= this confirms a candidate is the same
                    # recording (a re-encode). Below it the pair is kept as distinct variety.
                    # Frozen as validated (MANGLE=0); see architecture.md I3.


def _active_channels(gd):
    """channels PLAYED in a preset (static sound_channels + dynamic) on this install."""
    a = set()
    for _f, secs in parse_presets(gd).items():
        for _s, d in secs.items():
            a |= {c.lower() for c in d.get("base", [])} | {c.lower() for c in d.get("dynamic", [])}
    return a


def _base_played_files():
    """{md5: path} for every sound the install PLAYS. GAMMA winner = DSW's active
    channels (so its stripped channels are NOT counted - those are ours to restore);
    vanilla = its active channels resolved from the unpacked ambient tree."""
    files = {}
    dsw_act = _active_channels(GAMMA_WINNER)
    for gd in GAMMA_DEFINERS:
        root = Path(gd) / "sounds"
        for ch, d in parse_channels(gd).items():
            if ch.lower() in dsw_act:
                for st in d["stems"]:
                    f = resolve(st, root)
                    if f:
                        files.setdefault(file_hash(f), f)
    van_act = _active_channels(VAN_CFG)
    for ch, d in parse_channels(VAN_CFG).items():
        if ch.lower() in van_act:
            for st in d["stems"]:
                f = resolve(st, VAN_SND)
                if f:
                    files.setdefault(file_hash(f), f)
    return files


def _ensure_vanilla_unpacked():
    if VAN_SND.is_dir() and next(VAN_SND.rglob("*.ogg"), None):
        return
    import subprocess
    VAN_SND.parent.mkdir(parents=True, exist_ok=True)
    print(f"unpacking vanilla ambient sounds -> {VAN_SND.parent}")
    subprocess.run([CONVERTER, "-unpack", "-xdb", "-dir", str(VAN_SND.parent), VAN_DB], check=True)


def cmd_basedex(_a):
    """Build the base-played index (md5 + fingerprint + duration) -> base_index.json.
    Run once; plan reads it to drop duplicates. Rebuild when the install's ambient
    mods change (winner, DSW/Soundscape/RETUNE, or the vanilla pack)."""
    _ensure_vanilla_unpacked()
    files = _base_played_files()

    def one(hp):
        h, f = hp
        info = sp.probe(str(f)) or {}
        return {"md5": h, "fp": sp.fingerprint(str(f), FP_LEN),
                "dur": round(float(info.get("duration") or 0)), "path": str(f)}
    rows = sp.pmap(one, list(files.items()), sp.DEF_JOBS)
    (HERE / "base_index.json").write_text(json.dumps(rows), encoding="utf-8")
    print(f"base index: {len(rows)} played sounds (vanilla + GAMMA winner) -> base_index.json")


def _load_base_index():
    p = HERE / "base_index.json"
    if not p.exists():
        cmd_basedex(None)
    rows = json.loads(p.read_text())
    md5 = {r["md5"] for r in rows}
    by_dur = collections.defaultdict(list)
    for r in rows:
        if r["fp"]:
            by_dur[r["dur"]].append((r["fp"], r.get("path")))
    return md5, by_dur


def _base_dedup(merged):
    """Drop every chosen sound the install already plays: md5 hit, or acoustic
    fingerprint >= BASE_SIM to a base sound of the same duration (a re-encode)."""
    md5set, by_dur = _load_base_index()
    uniq = {c["abs"]: None for chan in merged for c in merged[chan]["chosen"]}
    for a in uniq:
        uniq[a] = file_hash(a)
    need = [a for a, h in uniq.items() if h not in md5set]
    fpres = dict(zip(need, sp.pmap(
        lambda a: (sp.fingerprint(a, FP_LEN), round(float((sp.probe(a) or {}).get("duration") or 0))),
        need, sp.DEF_JOBS)))

    def base_hit(a):
        if uniq[a] in md5set:
            return "md5"
        fp, dur = fpres.get(a, (None, 0))
        if not fp:
            return None
        pa = None
        for d in (dur - 1, dur, dur + 1):
            for bfp, bpath in by_dur.get(d, ()):
                if sp.fp_similarity(fp, bfp) >= BASE_SIM:
                    # Chromaprint only proposes; confirm with PCM cross-correlation so a
                    # sound the fingerprint wrongly matches to a base sound is not dropped.
                    if not bpath:
                        return "fp"                       # legacy index (no path): trust fp
                    if pa is None:
                        pa = sp.decode_pcm(a)
                    if sp.pcm_correlation(pa, sp.decode_pcm(bpath)) >= DEDUP_XCORR:
                        return "fp"
        return None
    hit = dict(zip(uniq, sp.pmap(base_hit, list(uniq), sp.DEF_JOBS)))
    n_md5 = sum(1 for v in hit.values() if v == "md5")
    n_fp = sum(1 for v in hit.values() if v == "fp")
    # Record the source hashes dropped as base-dups so the ledger books them by hash. The
    # ledger's own recheck is fingerprint-only, so it misses the re-encodes this stage caught
    # with fp + PCM xcorr; without this record those show as false UNUSED-DARK.
    (HERE / "base_dropped.json").write_text(
        json.dumps(sorted({uniq[a] for a, v in hit.items() if v})), encoding="utf-8")
    for chan in merged:
        merged[chan]["chosen"] = [c for c in merged[chan]["chosen"] if hit[c["abs"]] is None]
    print(f"base-dedup: dropped {n_md5} md5 + {n_fp} acoustic re-encodes the install already plays "
          f"(of {len(uniq)} chosen)")


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
    # 1b. manual fill for channels whose curated content does not resolve
    for chan, rule in MANUAL_FILL.items():
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
    # base-dedup: never ship a sound vanilla or the GAMMA winner already plays (md5 +
    # acoustic). Runs on the chosen set before it is frozen into merged_channels.json.
    _silence_gate(merged)
    _base_dedup(merged)
    _cross_channel_dedup(merged)
    (HERE / "merged_channels.json").write_text(json.dumps(merged, indent=1), encoding="utf-8")

    # 3. report
    print(f"mods merged: {[m[0] for m in MODS]}")
    net_new = sum(len(v["chosen"]) for v in merged.values())
    print(f"channels (union): {len(merged)}   filled: {sum(1 for v in merged.values() if v['chosen'])}   inherited (blowout/packed): {inherited}")
    print(f"sounds pooled: {tot_in}  ->  deduped {tot_kept}  ->  net-new after base-dedup: {net_new}  (dropped {tot_dropped}: exact dups + junk bitrate; {offrate} off-44100 skipped)")
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
SND = GDATA / "sounds/zs"              # zs\<channel>\N.ogg and zs\loop\<bed>\N.ogg
HDR = "; GENERATED"


def _clean(d):
    if d.exists():
        import shutil as sh
        sh.rmtree(d)


# ----------------------------------------------------------------------------
# The shipped model: two layers over the untouched engine bed.
#   LOOP - looped continuous beds, one at a time by context (as_loop.script).
#   EFFECT  - dynamic one-shots on the engine's own channels, enrich/restore/define
#             (see _channel_routing); grouped into 11 LAYERS for volume + density.
# Role is MEASURED per file (classify); the layer comes from layer_of.
# ----------------------------------------------------------------------------

# Vocal source channels: a wail/scream/spook is an EVENT, never a bed. Forced
# effect regardless of measured duration.
VOCAL = {"out_screams", "out_spooks", "out_mutants", "out_day_spoops", "out_night_spoops",
         "urban_spoops_night", "northen_spoops", "foliage_spook", "crows_spook"}

# The loop contexts (bed pool per source channel), separate from the effect layers.
# Loop pools = the looped beds the player hears one at a time. Underground is
# SPLIT by source-channel character into a LAB pool (machine/metal/voices/banging/
# lab hum - the X-Lab levels: X18, brain lab, war lab, X8) and a SEWER pool (drip/
# rats/noise/drone/ambient - tunnels, bunkers, agroprom underground), so a lab does
# not sound like a sewer. The material supports this split (the ugrnd_* channels are
# semantically distinct); it does NOT carry a per-level tag, so finer-than-class
# per-level underground pools would be invented, not traced - we do not do that.
BEDS = ["wind", "dread", "fog", "stormrain", "underground_lab", "underground_sewer"]
LOOP_CAP = 40                          # loop variations per pool; draws the held surplus
UG_LAB_CH = {"ugrnd_lab", "ugrnd_ambient_machine", "ugrnd_metal", "ugrnd_voices",
             "ugrnd_banging", "x18"}


def ctx_of(ch):
    c = ch.lower()
    if c.startswith("ugrnd_") or "underground_background" in c or c == "x18" or c == "inside_noise":
        return "underground"
    if "tuman" in c:
        return "fog"
    if "storm" in c or "rain" in c:
        return "stormrain"
    if "wind" in c:
        return "wind"
    return "dread"


def loop_pool(ch):
    """Loop pool for a source channel: the context bed, with underground split
    into lab vs sewer by channel character (UG_LAB_CH)."""
    c = ctx_of(ch)
    if c != "underground":
        return c
    return "underground_lab" if ch.lower() in UG_LAB_CH else "underground_sewer"


def _iter_chosen(mc):
    """Every chosen sound across all channels, in the canonical order
    (sorted channel name, then the channel's chosen order). This order defines
    classification.json and, downstream, the deployed N numbering."""
    for chan in sorted(mc):
        for c in mc[chan]["chosen"]:
            yield chan, c


# --- classify (measured role) ------------------------------------------------

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
    if chan in VOCAL:
        role = "effect"
    elif dur >= 30:
        role = "loop"
    elif dur < 4:
        role = "effect"
    else:
        role = "loop" if (crest < 12 and flat < 0.40) else "effect"
    bright = "dark" if cen < 2000 else ("mid" if cen < 4000 else "bright")
    tone = "tonal" if flat < 0.15 else ("mixed" if flat < 0.40 else "noisy")
    return {"ch": chan, "stem": c["stem"], "dur": dur, "cen": cen, "flat": flat,
            "crest": round(crest, 1), "role": role, "bright": bright, "tone": tone}


def cmd_classify(a):
    mc = json.loads((HERE / "merged_channels.json").read_text())
    items = list(_iter_chosen(mc))
    out = sp.pmap(lambda t: _classify_one(*t), items, sp.DEF_JOBS)
    dst = Path(a.out) if a.out else (HERE / "classification.json")
    dst.write_text(json.dumps(out, indent=1), encoding="utf-8")
    nt = sum(1 for r in out if r["role"] == "loop")
    print(f"classified {len(out)}: {nt} loop, {len(out) - nt} effect -> {dst.name}")


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

def _build_layers(mc, cls, ch_to_group, group_key):
    """Group the classified sounds into the deployed structure, deterministically.
    effects[group] = [entry,...] in canonical order; loops[bed] = top-LOOP_CAP by
    duration. classification.json is produced by classifying _iter_chosen(mc) in order,
    so cls[i] IS the classification of the i-th chosen entry - align POSITIONALLY, not by
    (ch,stem). Two chosen entries can share a stem (distinct sounds a pack shipped under
    one filename that PCM proved different); a (ch,stem) lookup collapsed them, dropping
    one and double-shipping the other. Positional alignment ships each exactly once."""
    chosen_seq = list(_iter_chosen(mc))
    assert len(cls) == len(chosen_seq), (
        f"classification.json ({len(cls)}) out of sync with merged_channels.json "
        f"({len(chosen_seq)}); rerun classify after plan")
    effects = {g: [] for g in group_key}
    loop_all = {b: [] for b in BEDS}
    for idx, (r, (ch, c)) in enumerate(zip(cls, chosen_seq)):
        assert r["ch"] == ch and r["stem"] == c["stem"], (
            f"classification out of sync with merged_channels at row {idx}; rerun classify")
        e = {"ch": ch, "stem": c["stem"], "abs": c["abs"], "pool": c["pool"],
             "dur": r["dur"], "idx": idx}
        if r["role"] == "loop":
            loop_all[loop_pool(ch)].append(e)
        elif ch in ch_to_group:          # skip effect sounds of bed channels (not routed)
            effects[ch_to_group[ch]].append(e)
    # dedup each bed across its pooled source channels, THEN cap - so the cap keeps LOOP_CAP
    # distinct loops, not LOOP_CAP slots some of which repeat.
    loops = {b: _dedup_entries(sorted(v, key=lambda e: (-e["dur"], e["idx"])))[:LOOP_CAP]
                for b, v in loop_all.items()}
    return effects, loops


def _emit_audio(entry, dst):
    # n107: ship every sound VERBATIM. No ffmpeg volume re-encode - it re-baked a lossy
    # gain AND dropped the source's X-Ray ogg comment blob (base_volume + min/max), which
    # reverts attenuation to the 1/300 default. Per-file loudness now rides in base_volume
    # (see _band_blobs, n108), not in the samples.
    dst.parent.mkdir(parents=True, exist_ok=True)
    import shutil as sh
    sh.copy2(entry["abs"], dst)


def _dep_names(entries):
    """Deployed file names, preserving the ORIGINAL name and path (entry stem = the
    source-relative path). A stem a pack shipped twice under one path (two distinct recordings
    PCM proved different) gets a __N suffix so the second never overwrites the first. Slashes
    stay posix here; callers backslash them for the LTX sounds= / path= references."""
    seen, names = {}, []
    for e in entries:
        stem = e["stem"]
        seen[stem] = seen.get(stem, 0) + 1
        names.append(stem if seen[stem] == 1 else f"{stem}__{seen[stem]}")
    return names


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


def _band_blobs(root):
    """Give blob-less files an X-Ray comment blob. Per channel folder, take the median
    (min, max) of the members that carry a blob and write it (base_volume 1.0) into the
    members that do not, so a blob-less file attenuates like its channel-mates instead of
    the 1/300 engine default; fall back to the global median for a folder with no carrier."""
    zs = root / "sounds/zs"
    scan, g_mins, g_maxs = {}, [], []
    for fld in {f.parent for f in zs.rglob("*.ogg")}:
        rows = [(f, _read_blob(f.read_bytes())) for f in sorted(fld.glob("*.ogg"))]
        scan[fld] = rows
        for _, b in rows:
            if b:
                g_mins.append(b[0]); g_maxs.append(b[1])
    g_min = _median(sorted(g_mins)) if g_mins else 1.0
    g_max = _median(sorted(g_maxs)) if g_maxs else 300.0
    wrote = skipped = 0
    for fld, rows in scan.items():
        cs = [b for _, b in rows if b]
        cmin = _median(sorted(c[0] for c in cs)) if cs else g_min
        cmax = _median(sorted(c[1] for c in cs)) if cs else g_max
        if cmax <= cmin:
            cmax = cmin + 1.0
        for f, b in rows:
            if b is None:
                if _write_blob(f, cmin, cmax, 1.0):
                    wrote += 1
                else:
                    skipped += 1
    print(f"blobs: wrote {wrote} X-Ray comment blobs (per-channel distance band, base_volume 1.0), "
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


_SETTINGS_CACHE = None


def _settings_key(ch):
    """The exact (min, max, periods, indoor, height) tuple for a source channel."""
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is None:
        mc = json.loads((HERE / "merged_channels.json").read_text())
        _SETTINGS_CACHE = {c: _chan_settings(mc[c].get("settings")) for c in mc}
    s = _SETTINGS_CACHE.get(ch) or _chan_settings(None)
    return (s["min"], s["max"], s["p"], s["indoor"], s["height"])


# --- layers + channel routing (the shipped model) ---------------------------
# A LAYER is a pure-purpose group of channels. Each deployed channel belongs to
# exactly one; the layer drives its MCM volume slider and the per-section density
# budget. Named for what the sound IS. layer_of is the single source of truth; the
# deploy materialises it to as_channel_layers.ltx so as_effect reads it, never a name.
LAYERS = ["spooks", "screams", "mutants", "ambience", "machines", "forest",
          "storm", "wind", "rain", "wildlife", "underground"]
# emission priority when a section is over the density budget: dread-core first,
# wildlife/rain last (effect colour). Layers not listed rank after these.
LAYER_ORDER = ["spooks", "screams", "mutants", "ambience", "underground", "forest",
               "storm", "wind", "machines", "rain", "wildlife"]


def layer_of(ch):
    c = ch.lower()
    if c.startswith("as_"):        # deployed define channels are as_<source>; layer by the source
        c = c[3:]
    if c.startswith("ugrnd_") or c == "x18" or c == "inside_noise" or "underground_background" in c:
        return "underground"
    if "rain" in c:
        return "rain"
    if "storm" in c or c == "pre_storm" or c == "chimes":
        return "storm"
    if "wind" in c:
        return "wind"
    if c in ("branch", "branch_med", "branch_big", "foliage_spook", "tree_sway_fog", "crows_spook"):
        return "forest"
    if c == "out_screams":
        return "screams"
    if c == "out_mutants":
        return "mutants"
    if c in ("out_dark_amb", "out_night_amb", "psi_sparks", "psistorm_background", "dark_signal"):
        return "ambience"
    if c in ("out_gunfire", "out_drone", "drones", "day_drones", "urban_drones", "vest_radio", "urban_debris"):
        return "machines"
    if c in ("crows", "crows_clear", "crows_forest", "crows_retune", "owls", "dogs", "birds_night"):
        return "wildlife"
    return "spooks"   # out_spooks, *_spoops: dark presence (default)


# strip-4: channels vanilla plays but the GAMMA winner (DSW) strips. We restore them
# on both installs (define fully + re-add to presets), filled with our net-new content.
STRIP4 = {"out_screams", "out_mutants", "out_gunfire", "wind_dark"}


def _channel_routing(mc, cls):
    """source channel -> (deployed, mode, layer) for every channel with EFFECT content.
      enrich  - a channel BOTH installs play: append our net-new sounds to it (deployed =
                the base name), NO preset change (it already plays where the base plays it).
      restore - a strip-4 channel: define fully + re-add to presets (deployed = base name).
      define  - a purpose no live base channel provides: our own as_<ch> (deployed = as_ch).
    Beds (loop role) are not routed here - the deploy sends them to the bed pools."""
    have_effect = {r["ch"] for r in cls if r["role"] != "loop"}
    both = _active_channels(VAN_CFG) & _active_channels(GAMMA_WINNER)
    gam_defined = set(parse_channels(GAMMA_WINNER).keys())   # channels DSW defines (played or not)
    routing = {}
    for ch in sorted(mc):
        if ch not in have_effect or not mc[ch]["chosen"]:
            continue
        if all(v == 0 for v in _chan_settings(mc[ch].get("settings"))["p"]):
            continue    # a bed (all periods 0) is a continuous loop -> the loop layer, never an effect
        lay = layer_of(ch)
        # AlifeSpooks is a standalone director now: every channel deploys as our OWN as_<ch>, never
        # enriching/restoring a base channel, so the vanilla ambient system never plays our sounds -
        # only as_effect does. (Old enrich/restore leaked our sounds through out_spooks/out_mutants/...)
        deployed = ch if ch.startswith("as_") else f"as_{ch}"
        routing[ch] = (deployed, "define", lay)
    return routing


def effect_group_map(cls):
    """(ch -> deployed channel, deployed channel -> settings key), derived from the
    routing. Deployed name = the base channel (enrich/restore) or as_<ch> (define).
    Kept as the shared entry point for _build_layers, deploy and provenance."""
    mc = json.loads((HERE / "merged_channels.json").read_text())
    routing = _channel_routing(mc, cls)
    ch_to_group, group_key = {}, {}
    for ch, (dep, _mode, _lay) in routing.items():
        ch_to_group[ch] = dep
        group_key[dep] = _settings_key(ch)
    return ch_to_group, group_key


EFFECT_PERIOD_FLOOR = 20000   # a period of 0 makes a one-shot fire every tick (spam); floor it.
                           # The source's 0 is recorded verbatim in provenance; only the deploy floors it.


# Play tuning - the EVOLVE step on the crystallized verbatim. The source period is kept
# verbatim in provenance.tsv; the DEPLOYED period is tuned so effects stay DISCRETE and
# thin channels do not repeat:
#   - discrete: period >= sound duration + a gap, so a long sound never overlaps itself
#     (a 12s storm on a 5s period is a wall of noise, not an effect).
#   - variety-weighted: a channel with few sounds fires proportionally less, so its handful
#     is spread out instead of spammed. A rich channel keeps the discrete rate.
DISCRETE_GAP = 8000        # ms guaranteed after a sound before the channel may re-fire
VARIETY_TARGET = 20        # a channel needs about this many sounds to fire at the discrete rate
VARIETY_MAX_STRETCH = 6    # cap the thin-channel slow-down so it is rare, not silent


def _tune_period(p, dur_ms, size):
    base = max(p, dur_ms + DISCRETE_GAP)
    if size and size < VARIETY_TARGET:
        base = int(base * min(VARIETY_MAX_STRETCH, VARIETY_TARGET / size))
    return base


def _effect_settings(key, dur_ms=0, size=0):
    mn, mx, p, indoor, height = key
    lines = [f"min_distance = {mn}", f"max_distance = {mx}"]
    for i, pv in enumerate(p):
        lines.append(f"period{i} = {_tune_period(pv if pv > 0 else EFFECT_PERIOD_FLOOR, dur_ms, size)}")
    lines.append(f"height = {height}")
    if indoor:
        lines.append("indoor = true")
    return lines


def deploy_loop(root, loops):
    """Emit the loop layer only (loop\\<pool>\\N.ogg + looped themes + bed list),
    leaving the effect tree untouched. Separated so the loop pools can be rebuilt
    without re-encoding the effects (an ffmpeg re-encode is not byte-deterministic)."""
    snd = root / "sounds/zs"
    _clean(snd / "loop")
    (root / "configs/scripts").mkdir(parents=True, exist_ok=True)
    (root / "configs/misc/sound").mkdir(parents=True, exist_ok=True)
    themes, beds_cfg = [HDR], [HDR, "[beds]"]
    beds_cfg += [b for b in BEDS if loops[b]]
    for bed in BEDS:
        entries = loops[bed]
        if not entries:
            continue
        fnames = _dep_names(entries)
        for e, fnm in zip(entries, fnames):
            _emit_audio(e, snd / "loop" / bed / (fnm + ".ogg"))
        names = [f"as_loop_{bed}_{i}" for i in range(1, len(entries) + 1)]
        for nm, fnm in zip(names, fnames):
            themes += [f"[{nm}]", "type = looped", "path = zs\\loop\\" + bed + "\\" + fnm.replace("/", "\\"), ""]
        beds_cfg += [f"\n[{bed}]", "themes = " + ", ".join(names)]
    (root / "configs/misc/sound/mod_script_sound_as.ltx").write_text("\n".join(themes), encoding="utf-8")
    (root / "configs/scripts/as_loop_beds.ltx").write_text("\n".join(beds_cfg) + "\n", encoding="utf-8")


def cmd_deploy(a):
    root = Path(a.root) if a.root else GDATA
    env = root / "configs/environment"
    snd = root / "sounds/zs"
    mc = json.loads((HERE / "merged_channels.json").read_text())
    cls = json.loads((HERE / "classification.json").read_text())
    routing = _channel_routing(mc, cls)
    ch_to_group = {ch: dep for ch, (dep, _m, _l) in routing.items()}
    group_key = {dep: _settings_key(ch) for ch, (dep, _m, _l) in routing.items()}
    dep_mode = {dep: mode for _ch, (dep, mode, _l) in routing.items()}
    dep_layer = {dep: lay for _ch, (dep, _m, lay) in routing.items()}
    effects, loops = _build_layers(mc, cls, ch_to_group, group_key)

    _clean(snd); _clean(env / "ambients")
    (root / "configs/scripts").mkdir(parents=True, exist_ok=True)
    (root / "configs/misc/sound").mkdir(parents=True, exist_ok=True)
    (env / "ambients/presets").mkdir(parents=True, exist_ok=True)

    # Deployed effect channels. @[C] is the DLTX safe create-or-override: it MERGES our
    # sounds into an existing channel (enrich/restore) or CREATES it (define). Sounds are
    # always appended with >sounds so a base channel's own sounds are never replaced; a
    # define channel additionally carries its settings and a seeding `sounds =` line.
    # ONE sound per line - a single long `sounds = a,b,c,...` overflows the engine's fixed
    # LTX read buffer (IReader::r_string, FS.cpp) and CTDs at load.
    chan_lines, layer_lines = [HDR], [HDR, "[as_channel_layers]"]
    for dep in sorted(effects):
        entries = effects[dep]
        if not entries:
            continue
        names = _dep_names(entries)
        for e, nm in zip(entries, names):
            _emit_audio(e, snd / dep / (nm + ".ogg"))
        chan_lines.append(f"@[{dep}]")
        if dep_mode[dep] == "define":
            durs = sorted(e["dur"] for e in entries)
            dur_ms = int(durs[len(durs) // 2] * 1000) if durs else 0
            chan_lines.extend(_effect_settings(group_key[dep], dur_ms, len(entries)))
            chan_lines.append("sounds = zs\\" + dep + "\\" + names[0].replace("/", "\\"))
            rest = names[1:]
        else:                       # enrich / restore: append only, inherit the base settings
            rest = names
        for nm in rest:
            chan_lines.append(">sounds = zs\\" + dep + "\\" + nm.replace("/", "\\"))
        chan_lines.append("")
        layer_lines.append(f"{dep} = {dep_layer[dep]}")
    # Also map the base's OWN dark channels (the install plays them, we ship no content for
    # them), so the per-layer volume governs the WHOLE dark soundscape, not just our additions.
    # as_effect applies the layer to every dynamic channel it plays, ours or the base's; a base
    # channel absent from the map would only obey the global knob. Beds are skipped (never a
    # dynamic effect). Non-effect nature stays out (DARK_KEEP is dark-scoped).
    mapped = {ln.split(" = ", 1)[0] for ln in layer_lines[2:]}
    base_active = (_active_channels(VAN_CFG) | _active_channels(GAMMA_WINNER)) & DARK_KEEP
    for ch in sorted(base_active):
        if ch in mapped or "background" in ch or ch.endswith("_bkg_1"):
            continue
        layer_lines.append(f"{ch} = {layer_of(ch)}")
    (env / "mod_sound_channels_alifespooks.ltx").write_text("\n".join(chan_lines), encoding="utf-8")
    (env / "as_channel_layers.ltx").write_text("\n".join(layer_lines) + "\n", encoding="utf-8")

    _band_blobs(root)
    # Standalone director: no loop layer, no preset placement. Every channel is our own as_<ch>,
    # played only by as_effect; the vanilla ambient system never references them.
    print(f"deployed to {root}")
    print(f"  effect channels: {len(effects)} define; {sum(len(v) for v in effects.values())} sounds")


# --- distribution: which channel plays in which (level, time, weather) section -----
# EVIDENCE + LORE + BUDGET. A restore/define channel plays where a source pack placed
# its source channel (the section name carries time + weather, so night-heavier dread,
# animals-by-time and weather-gating fall out of the placement), refined by two lore
# rules (underground labs, the haunted whisper level), then capped so base + our added
# channels never exceed vanilla's per-section maximum. ENRICH channels are NOT placed
# here - they already play wherever the base plays them; we only added sounds to them.
SECTION_MAX = 13    # vanilla's observed per-section channel ceiling; keep total <= this
UNDERGROUND_LEVELS = {"environment_underground", "environment_underground_more",
                      "environment_underground_x18"}
WHISPER_LEVEL = "environment_whisper"


def _place_map(routing):
    """source channel -> deployed name, for the channels we PLACE (restore + define).
    Enrich channels are excluded: they already play wherever the base plays them."""
    return {ch: dep for ch, (dep, mode, _l) in routing.items() if mode in ("restore", "define")}


def _section_channels(fname, sec, place, routing):
    """Deployed restore/define channels to place at (level fname, section sec):
    evidenced (a source pack placed the source channel there), lore-refined for the
    underground labs and the haunted whisper level. Returns deployed channel names."""
    stem = fname[:-4]
    lay = {dep: layer_of(dep) for dep in place.values()}
    if stem in UNDERGROUND_LEVELS:                    # labs: underground channels, indoor only
        if not sec.lower().startswith("indoor"):
            return []
        return sorted({dep for dep in place.values() if lay[dep] == "underground"})
    srcs = set()
    for pm in _PER_PACK.values():
        srcs |= set(pm.get(fname, {}).get(sec, {}).get("dynamic", []))
    # RESTORE channels (a strip-4 channel the winner strips but still defines) are placed
    # in a dynamic list only by VANILLA's own presets, which _PER_PACK excludes; add
    # vanilla evidence for restore channels only, so the restore actually happens (e.g.
    # out_screams / wind_dark in forest/swamp/whisper). Scoped to restore so define
    # placement is unchanged.
    restore_src = {ch for ch, (dep, mode, _l) in routing.items() if mode == "restore"}
    if restore_src:
        van_dyn = _VANILLA_PRESETS.get(fname, {}).get(sec, {}).get("dynamic", [])
        srcs |= {c for c in van_dyn if c in restore_src}
    deps = {place[c] for c in srcs if c in place}
    if stem == WHISPER_LEVEL:                         # haunted: no wildlife, no people
        deps = {d for d in deps if lay[d] not in ("wildlife", "machines")}
    return sorted(deps)


_PER_PACK = {}
_VANILLA_PRESETS = {}


def _level_preset_map():
    """level.name() -> preset stem, resolved the way the engine resolves it on GAMMA.
    Dark Signal rebinds each level stub to its area preset (l02_garbage -> environment_garbage);
    levels DS does not rebind keep vanilla's stub (e.g. the underground levels). This is the
    same binding the clone hits when it opens environment\\ambients\\<level>.ltx, so keying
    placement by level.name() lines up with what plays there."""
    def read_dir(gd):
        m = {}
        d = Path(gd) / "configs/environment/ambients"
        if not d.is_dir():
            return m
        for f in d.glob("*.ltx"):
            hit = re.search(r"environment_[a-z0-9_]+", f.read_text(encoding="utf-8", errors="replace"))
            if hit:
                m[f.stem] = hit.group(0)
        return m
    m = read_dir(VAN_CFG)              # vanilla stubs (fallback)
    m.update(read_dir(GAMMA_WINNER))   # Dark Signal's rebinds win
    return m


def write_placement(env, routing):
    """Emit configs/scripts/as_placement.ltx: per level, per section, our restore/define
    channels. The clone (as_effect.reset_settings) reads this and appends them to the
    section's channel list at runtime. This is the delivery that works: DLTX cannot patch
    the ambient presets, because the engine opens the per-level stub and #includes the preset,
    and DLTX does not merge into #included files (doc/library/modding/dltx.md, the root-file
    rule). Capped so the winner's base count + our additions stays <= SECTION_MAX; over budget,
    dropped by LAYER_ORDER (dread-core kept, wildlife/rain first out). Enrich channels are not
    listed - they play wherever the base plays them."""
    global _PER_PACK, _VANILLA_PRESETS
    _PER_PACK = {name: parse_presets(gd) for name, gd in MODS if name != "vanilla"}
    _VANILLA_PRESETS = parse_presets(VAN_CFG)
    base = parse_presets(GAMMA_WINNER)
    place = _place_map(routing)
    lay = {dep: layer_of(dep) for dep in place.values()}
    level_map = _level_preset_map()

    def budget_cap(deps, base_count):
        room = SECTION_MAX - base_count
        if room <= 0:
            return []
        if len(deps) <= room:
            return deps

        def rank(d):
            l = lay.get(d, "spooks")
            return (LAYER_ORDER.index(l) if l in LAYER_ORDER else len(LAYER_ORDER), d)
        return sorted(sorted(deps, key=rank)[:room])

    lines = [HDR, ""]
    for level in sorted(level_map):
        secs = base.get(level_map[level] + ".ltx")
        if not secs:
            continue
        body = []
        for sec in secs:
            deps = budget_cap(_section_channels(level_map[level] + ".ltx", sec, place, routing),
                              len(secs[sec].get("dynamic", [])))
            if deps:
                body.append(f"{sec} = " + ", ".join(deps))
        if body:
            lines.append(f"[{level}]")
            lines.extend(body)
            lines.append("")
    (env.parent / "scripts").mkdir(parents=True, exist_ok=True)
    (env.parent / "scripts" / "as_placement.ltx").write_text("\n".join(lines), encoding="utf-8")


def cmd_placement(a):
    root = Path(a.root) if a.root else GDATA
    env = root / "configs/environment"
    mc = json.loads((HERE / "merged_channels.json").read_text())
    cls = json.loads((HERE / "classification.json").read_text())
    routing = _channel_routing(mc, cls)
    write_placement(env, routing)
    # remove the old, inert preset patches (they never merged - presets are #include-only)
    old = root / "configs/environment/ambients/presets"
    n = 0
    if old.is_dir():
        for f in list(old.glob("mod_environment_*_alifeambience.ltx")):
            f.unlink(); n += 1
    print(f"placement -> configs/scripts/as_placement.ltx  (removed {n} inert preset patches)")


# --- ledger (the content-hash proof: UNUSED-DARK must be 0) -------------------

DARK_KW = ["spook", "spoop", "mutant", "scream", "distant", "amb_dark", "amb_night",
           "dark_amb", "ugrnd", "underground", "/metal", "banging", "rats", "drip",
           "/drone", "/noise", "whisper", "thunder", "storm", "shooting", "wind_dark",
           "tuman", "creep", "howl", "moan", "growl", "northern", "pre_storm"]
EMISSION_KW = ["blowout", "psi_storm", "emission"]
INCLUDE_ROOTS = ["ambient", "ambience_exp", "nature", "anomaly"]


def cmd_ledger(a):
    mc = json.loads((HERE / "merged_channels.json").read_text())
    cls = json.loads((HERE / "classification.json").read_text())
    role = {(r["ch"], r["stem"]): r["role"] for r in cls}
    chosen = {}                                        # source hash -> (ch, stem)
    for ch, c in _iter_chosen(mc):
        chosen[file_hash(c["abs"])] = (ch, c["stem"])
    deployed = set()                                   # AUDIO hashes actually shipped - n108
    zs = GDATA / "sounds/zs"                            # rewrites comment headers, so a shipped
    for f in zs.rglob("*.ogg"):                         # file's BYTES differ from source while its
        deployed.add(_audio_hash(f))                    # audio does not; match blob-agnostic.
    base_md5, base_by_dur = _load_base_index()         # sounds the install already PLAYS
    ip = HERE / "intra_dups.json"                       # our own re-encodes the PCM dedup dropped
    intra_dropped = set(json.loads(ip.read_text())) if ip.exists() else set()
    def _load_set(fn):
        p = HERE / fn
        return set(json.loads(p.read_text())) if p.exists() else set()
    base_dropped = _load_set("base_dropped.json")       # dropped as install-plays-it (fp + xcorr)
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
            elif h in chosen and role.get(chosen[h]) != "loop":
                st = "USED-effect-unshipped"
            elif h in chosen:
                st = "HELD-loop-surplus"
            elif emission:
                st = "EMISSION-excluded"
            elif h in base_md5:                         # the install plays it (exact) -> not ours
                st = "BASE-DUP-excluded"
            elif h in intra_dropped:                    # our own re-encode, deduped by cross-correlation
                st = "INTRA-DUP-excluded"
            elif h in silence_dropped:                  # dead/empty, dropped by the silence gate
                st = "SILENCE-excluded"
            elif h in base_dropped:                     # the install plays it, dropped by base-dedup
                st = "BASE-DUP-excluded"
            elif dark and under_root:
                info = sp.probe(str(f)) or {}
                if info.get("sample_rate") != 44100:
                    st = "OFFSPEC-48k-excluded"
                else:
                    pending.append((name, rel, f))      # decide UNUSED-DARK vs BASE-DUP acoustically
                    continue
            elif under_root:
                st = "off-scope-or-dup"
            else:
                st = "SKIP-nonambient"
            rows.append(f"{name}\t{rel}\t{st}")
            counts[st] += 1
    # a dark file the install doesn't byte-match may still be a re-encoded copy - either of a
    # sound the install plays (BASE-DUP) or of one WE ship that the PCM dedup dropped (INTRA-DUP,
    # captured-then-deduped, not missed). Fingerprint the residue against both indexes so
    # UNUSED-DARK counts only TRUE misses (a net-new dark sound left uncaptured).
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
            if any(sp.fp_similarity(fp, b) >= BASE_SIM for d in ds for b, _bp in base_by_dur.get(d, ())):
                st = "BASE-DUP-excluded"
            elif any(sp.fp_similarity(fp, b) >= BASE_SIM for d in ds for b in chosen_by_dur.get(d, ())):
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
    ch_to_group, group_key = effect_group_map(cls)
    effects, loops = _build_layers(mc, cls, ch_to_group, group_key)
    settings = {ch: _parse_settings(mc[ch]["settings"]) for ch in mc}
    ch_sec = _channel_sections()
    zs = GDATA / "sounds/zs"

    cols = ["deployed", "layer", "group", "orig_mod", "orig_dir", "orig_file", "orig_channel",
            "min_distance", "max_distance", "period0", "period1", "period2", "period3",
            "indoor", "height", "base_volume", "orig_sections"]
    rows, verify_ok, verify_bad = [], 0, 0
    def add(entries, layer, group, reldir):
        nonlocal verify_ok, verify_bad
        names = _dep_names(entries)
        for e, nm in zip(entries, names):
            dep = "zs\\" + reldir + "\\" + nm.replace("/", "\\")
            s = settings.get(e["ch"], {})
            stem = e["stem"]
            dfile = zs / Path(reldir.replace("\\", "/")) / (nm + ".ogg")
            # n107/n108: every file ships audio-verbatim; a blob write touches only the
            # comment header. Record the DEPLOYED base_volume and self-verify by AUDIO.
            bv = ""
            if dfile.exists():
                b = _read_blob(dfile.read_bytes())
                if b:
                    bv = round(b[2], 3)
                if _audio_hash(dfile) == _audio_hash(Path(e["abs"])):
                    verify_ok += 1
                else:
                    verify_bad += 1
            rows.append([dep, layer, group, e["pool"], str(Path(stem).parent).replace("\\", "/"),
                         Path(stem).name, e["ch"],
                         s.get("min_distance", ""), s.get("max_distance", ""),
                         s.get("period0", ""), s.get("period1", ""), s.get("period2", ""), s.get("period3", ""),
                         s.get("indoor", ""), s.get("height", ""),
                         str(bv), "; ".join(ch_sec.get(e["ch"], []))])
    for g in sorted(group_key):                       # effects deploy to zs\<channel>\N
        add(effects[g], layer_of(g), g, g)
    for bed in BEDS:                                  # loop beds to zs\loop\<bed>\N
        add(loops[bed], "loop", bed, f"loop\\{bed}")
    lines = ["\t".join(cols)] + ["\t".join(r) for r in rows]
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
    sub.add_parser("basedex").set_defaults(func=cmd_basedex)
    p = sub.add_parser("classify"); p.add_argument("--out"); p.set_defaults(func=cmd_classify)
    p = sub.add_parser("loudness"); p.add_argument("--out"); p.set_defaults(func=cmd_loudness)
    p = sub.add_parser("deploy"); p.add_argument("--root"); p.set_defaults(func=cmd_deploy)
    p = sub.add_parser("placement"); p.add_argument("--root"); p.set_defaults(func=cmd_placement)
    sub.add_parser("ledger").set_defaults(func=cmd_ledger)
    sub.add_parser("provenance").set_defaults(func=cmd_provenance)
    a = ap.parse_args(); a.func(a)
