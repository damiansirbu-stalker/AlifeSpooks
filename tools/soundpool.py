#!/usr/bin/env python3
"""soundpool.py - probe + dedup primitives for the AlifeSpooks pipeline.

`merge.py` is the pipeline (plan/classify/loudness/deploy/ledger/provenance); this module holds only the
shared low-level primitives it imports: external-tool resolution, a parallel map, ffprobe metadata, the
Chromaprint fingerprint + similarity, and the PCM cross-correlation same-recording decider. Standard
library only; drives ffprobe, ffmpeg, and fpcalc (Chromaprint) as external CLIs.

The older standalone CLI (inventory/select/generate/validate over a `pools.json`, emitting a
`sound_channels.ltx`) was retired when merge.py replaced the channel model with structural per-file capture
+ the manifest + the DLTX veto. It is not this module's job any more.

External tools resolve from $PORTX_ROOT/packages (default C:/App/PORTX), or $FFPROBE / $FFMPEG / $FPCALC
overrides, or PATH.
"""

import array
import json
import math
import os
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
    fmt = j.get("format") or {}

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    br = num(st.get("bit_rate")) or num(fmt.get("bit_rate"))
    return {
        "codec": st.get("codec_name"),
        "sample_rate": int(num(st.get("sample_rate")) or 0),
        "channels": int(num(st.get("channels")) or 0),
        "duration": num(st.get("duration")) or num(fmt.get("duration")) or 0.0,
        "bit_rate": int(br) if br else 0,
        "size": int(num(fmt.get("size")) or 0),
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
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    bits = sum((a[i] ^ b[i]).bit_count() for i in range(n))
    return 1.0 - bits / (32.0 * n)


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


def _pcm_norm(v):
    if not v:
        return v
    m = sum(v) / len(v)
    d = [x - m for x in v]
    e = math.sqrt(sum(x * x for x in d)) or 1.0
    return [x / e for x in d]


def _pcm_best_offset(e1, e2):
    """Coarse alignment: envelope offset (in samples) maximizing envelope correlation."""
    a, b = _pcm_norm(e1), _pcm_norm(e2)
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
    n = min(len(x), len(y))
    if n < 50:
        return 0.0
    x, y = x[:n], y[:n]
    mx, my = sum(x) / n, sum(y) / n
    sx = sy = sxy = 0.0
    for i in range(n):
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
