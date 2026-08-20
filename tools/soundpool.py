#!/usr/bin/env python3
"""soundpool.py - probe + dedup primitives for the AlifeSpooks pipeline.

`build.py` is the pipeline (plan/classify/loudness/deploy/ledger/provenance); this module holds only the
shared low-level primitives it imports: external-tool resolution, a parallel map, ffprobe metadata, the
Chromaprint fingerprint + similarity, the PCM cross-correlation same-recording decider, and the stereo->mono
masterization. Standard library only; drives ffprobe, ffmpeg, and fpcalc (Chromaprint) as external CLIs.

These primitives carry no AlifeSpooks concepts (no categories, routing, manifest, or veto), so any sound
pipeline can reuse them: probe/dedup a pool, fold stereo to mono, measure loudness. The project-specific
driver (routing, scope, output layout) lives in build.py; this file is the reusable core.

The older standalone CLI (inventory/select/generate/validate over a `pools.json`, emitting a
`sound_channels.ltx`) was retired when build.py replaced the channel model with structural per-file capture
+ the manifest + the DLTX veto. It is not this module's job any more.

External tools resolve from $PORTX_ROOT/packages (default C:/App/PORTX), or $FFPROBE / $FFMPEG / $FPCALC
overrides, or PATH.
"""

import array
import json
import math
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORTX_ROOT = Path(os.environ.get("PORTX_ROOT", "C:/App/PORTX"))
DEF_JOBS = min(16, (os.cpu_count() or 4))

# tool -> (env var, portx package, exe name)
_TOOLS = {
    "ffprobe": ("FFPROBE", "ffmpeg", "ffprobe.exe"),
    "ffmpeg": ("FFMPEG", "ffmpeg", "ffmpeg.exe"),
    "fpcalc": ("FPCALC", "chromaprint", "fpcalc.exe"),
}


def tool(name):
    env, pkg, exe = _TOOLS[name]
    override = os.environ.get(env)
    if override:
        return override
    cand = PORTX_ROOT / "packages" / pkg / exe
    if cand.exists():
        return str(cand)
    found = shutil.which(name)
    if found:
        return found
    sys.exit(f"error: cannot find {name} (set ${env} or install to {cand})")


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")


def pmap(fn, items, jobs):
    """Parallel map. subprocess calls release the GIL while waiting, so threads
    give real concurrency for the external-CLI workload."""
    items = list(items)
    if jobs <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        return list(ex.map(fn, items))


# --- probes ---------------------------------------------------------------

def probe(path):
    r = run([tool("ffprobe"), "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name,sample_rate,channels,duration,bit_rate",
             "-show_entries", "format=bit_rate,size", "-of", "json", path])
    if r.returncode != 0:
        return None
    try:
        j = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None
    st = (j.get("streams") or [{}])[0]
    container = j.get("format") or {}

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    br = num(st.get("bit_rate")) or num(container.get("bit_rate"))
    return {
        "codec": st.get("codec_name"),
        "sample_rate": int(num(st.get("sample_rate")) or 0),
        "channels": int(num(st.get("channels")) or 0),
        "duration": num(st.get("duration")) or num(container.get("duration")) or 0.0,
        "bit_rate": int(br) if br else 0,
        "size": int(num(container.get("size")) or 0),
    }


def fingerprint(path, length):
    r = run([tool("fpcalc"), "-raw", "-length", str(length), path])
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        if line.startswith("FINGERPRINT="):
            try:
                return [int(x) & 0xFFFFFFFF for x in line[12:].split(",") if x]
            except ValueError:
                return None
    return None


def fp_similarity(a, b):
    count = min(len(a), len(b))
    if count == 0:
        return 0.0
    bits = sum((a[i] ^ b[i]).bit_count() for i in range(count))
    return 1.0 - bits / (32.0 * count)


# --- PCM cross-correlation: the same-recording decider (architecture.md I3) -----
# Chromaprint proposes candidates (recall) but cannot decide - its similarity ranges
# for same-vs-distinct overlap (a distinct sound can score 1.0, a re-encode 0.93).
# md5 alone misses re-encodes. The decider is the normalized cross-correlation of the
# decoded waveforms: a re-encode correlates ~1.0, a genuinely distinct sound ~0. The
# constants below are FROZEN as validated (MANGLE=0 over the corpus); do not tune them
# without re-running the same-vs-distinct separation check.
PCM_RATE = 4000            # decode sample rate (Hz); enough to capture pitch + transients
PCM_ENV_FRAME = 100        # envelope frame (samples) for the coarse offset search
PCM_REFINE = 120           # sample window around the envelope offset for the fine search
PCM_REFINE_STEP = 6        # stride of the fine search
_PCM_SILENCE = 150         # |sample| below this is treated as silence when trimming ends


def decode_pcm(path):
    """Decode to a mono list of int16 samples at PCM_RATE, near-silence trimmed off
    both ends (so leading/trailing padding differences do not defeat alignment)."""
    r = subprocess.run([tool("ffmpeg"), "-v", "error", "-i", path, "-ac", "1",
                        "-ar", str(PCM_RATE), "-f", "s16le", "-"], capture_output=True)
    a = array.array("h")
    a.frombytes(r.stdout)
    a = a.tolist()
    lo, hi = 0, len(a)
    while lo < hi and abs(a[lo]) < _PCM_SILENCE:
        lo += 1
    while hi > lo and abs(a[hi - 1]) < _PCM_SILENCE:
        hi -= 1
    return a[lo:hi]


def _pcm_envelope(a):
    F = PCM_ENV_FRAME
    return [math.sqrt(sum(a[i + k] * a[i + k] for k in range(F)) / F)
            for i in range(0, len(a) - F, F)]


def _normalize_pcm(v):
    if not v:
        return v
    m = sum(v) / len(v)
    d = [x - m for x in v]
    e = math.sqrt(sum(x * x for x in d)) or 1.0
    return [x / e for x in d]


def _pcm_best_offset(e1, e2):
    """Coarse alignment: envelope offset (in samples) maximizing envelope correlation."""
    a, b = _normalize_pcm(e1), _normalize_pcm(e2)
    if not a or not b:
        return 0
    bo, bs = 0, -2.0
    for off in range(-len(a) + 1, len(b)):
        s = sum(x * y for x, y in zip(a[max(0, off):], b[max(0, -off):]))
        if s > bs:
            bs, bo = s, off
    return bo * PCM_ENV_FRAME


def _pcm_pearson_at(a, b, off):
    if off >= 0:
        x, y = a[off:], b
    else:
        x, y = a, b[-off:]
    count = min(len(x), len(y))
    if count < 50:
        return 0.0
    x, y = x[:count], y[:count]
    mx, my = sum(x) / count, sum(y) / count
    sx = sy = sxy = 0.0
    for i in range(count):
        dx, dy = x[i] - mx, y[i] - my
        sx += dx * dx
        sy += dy * dy
        sxy += dx * dy
    return sxy / (math.sqrt(sx * sy) or 1.0)


def pcm_correlation(samples_a, samples_b):
    """Same-recording confidence in [-1, 1]: normalized cross-correlation of two decoded
    PCM signals (from decode_pcm), aligned by envelope offset then refined by Pearson
    over the overlap. ~1.0 = the same recording (re-encode); ~0 = a distinct sound.
    Robust to bitrate, codec and silence padding."""
    if not samples_a or not samples_b:
        return 0.0
    off = _pcm_best_offset(_pcm_envelope(samples_a), _pcm_envelope(samples_b))
    best = -2.0
    for o in range(off - PCM_REFINE, off + PCM_REFINE + 1, PCM_REFINE_STEP):
        r = _pcm_pearson_at(samples_a, samples_b, o)
        if r > best:
            best = r
    return best


# --- stereo -> mono masterization ------------------------------------------
# The engine 3D-positions MONO only; it force-2Ds any 2-channel buffer to at-ear, full volume
# (SoundRender_Core.cpp:344,368,391), so a POSITIONED one-shot has to be mono. Fold a stereo file
# by its mid/side energy: (L+R)/2 by default (the standard downmix, energy-preserving for a
# correlated image), but keep one channel where the two are ANTI-PHASE and summing would cancel
# (mid=(L+R)/2 -> ~silence while side=(L-R)/2 stays loud). The measured mid/side peaks decide.
STEREO_ENCODE_Q   = 6      # libvorbis -q for the mono re-encode: high quality, deterministic (no dither)
SIDE_ANTIPHASE_DB = 3.0    # side RMS this many dB ABOVE mid RMS -> anti-phase, sum cancels -> drop a channel.
                           # RMS (energy), not peak: a localized transient can spike the side peak on a
                           # correlated file, but only sustained opposition (side energy > sum energy) means
                           # summing actually loses the signal. Measured gap: anti-phase +4.5..+7.3, wide -8..-13.


def _mid_side_rms_db(path):
    """RMS dB of the mid (L+R)/2 and side (L-R)/2 of a stereo file, or (None, None) on failure.
    A correlated (summable) file has side well below mid; an anti-phase file has side at or above mid."""
    r = run([tool("ffmpeg"), "-v", "info", "-i", str(path), "-af",
             "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0-0.5*c1,astats=metadata=1:reset=0", "-f", "null", "-"])
    rms = re.findall(r"RMS level dB:\s*(-?inf|[-\d.]+)", r.stderr)
    if len(rms) < 2:
        return None, None

    def _db(x):
        return -120.0 if x in ("-inf", "inf") else float(x)

    return _db(rms[0]), _db(rms[1])


def stereo_method(path):
    """How to fold `path` to mono: 'mono' (already 1 channel, leave it), 'sum' ((L+R)/2, the
    default), or 'drop' (keep one channel, only when the pair is anti-phase and summing cancels).
    A surround/multichannel file (>2) has no mid/side, so it downmixes via 'sum' (-ac 1)."""
    ch = (probe(path) or {}).get("channels", 0)
    if ch < 2:
        return "mono"
    if ch > 2:
        return "sum"
    mid, side = _mid_side_rms_db(path)
    if mid is None:
        return "sum"
    return "drop" if side - mid > SIDE_ANTIPHASE_DB else "sum"


def fold_to_mono(src, dst, method):
    """Re-encode `src` to a mono 44100 Hz vorbis ogg at `dst`. method 'sum' = -ac 1 ((L+R)/2);
    'drop' = keep the left channel (anti-phase). libvorbis at STEREO_ENCODE_Q, input metadata
    stripped, so the AUDIO pages are byte-deterministic across runs (a re-fold reproduces the same
    file - what makes a re-add idempotent). Returns True on success. Does NOT write the X-Ray blob;
    the driver does that afterwards (loudness/min-max are a separate, project-level concern."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    af = ["-ac", "1"] if method == "sum" else ["-af", "pan=mono|c0=c0"]
    r = run([tool("ffmpeg"), "-y", "-v", "error", "-i", str(src), *af, "-ar", "44100",
             "-c:a", "libvorbis", "-q:a", str(STEREO_ENCODE_Q), "-map_metadata", "-1", str(dst)])
    return r.returncode == 0 and dst.exists()


def to_mono(src, dst):
    """One-call fold: classify `src`, then produce a mono ogg at `dst`. Returns the method used -
    'copy' (already mono, byte-verbatim so any source X-Ray blob survives), 'sum', 'drop', or None
    on encode failure. The reusable entry point a driver calls per file."""
    method = stereo_method(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if method == "mono":
        shutil.copy2(src, dst)
        return "copy"
    return method if fold_to_mono(src, dst, method) else None
