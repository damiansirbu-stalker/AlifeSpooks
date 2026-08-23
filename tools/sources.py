"""Source registry for the AlifeSpooks sound pipeline (n124).

One declarative entry per source pack. Sources are ALWAYS pulled locally by hand - the pipeline never
downloads anything. `url` is a REFERENCE link only (the moddb / origin page), kept for credit and provenance
(readme, licensing). The build reads `path`; a source missing there is reported by `build.py provision` and
must be fetched by you. This keeps every shipped sound traceable to a recorded origin without any network step.

ORDER IS LOAD-BEARING: dedup (dedupe) is mildly order-sensitive, so the entries stay in the exact order
the old hardcoded MODS list used - reordering can change which copy of a duplicate wins and shift the corpus.

Per entry:
  name    - the id used across the pipeline (MODS, provenance, the report).
  path    - local gamedata dir (or the extracted root for standalone builds). What the build reads.
  url     - reference/credit link (moddb addon page or origin). None where there is none (granted-original,
            base game, or just not recorded). Purely informational - nothing fetches it.
  licence - "free": public moddb addon, free with credit. "permission": granted directly, proof in the note.
            "game": base game / standalone STALKER build, credited. "pending": not cleared -> the build STOPS.
"""

SOURCES = [
    {"name": "Amplified", "licence": "free",
     "url": "https://www.moddb.com/mods/stalker-anomaly/addons/dark-signal-amplified-soundscape",
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/audio/Dark Signal Amplified Soundscape/gamedata"},
    # AmplifiedVanilla EXCLUDED: it is the same amplified audio as Amplified in a vanilla-WEATHER config
    # (weathers/ vs bck/). PROVEN redundant 2026-08-18: all 4988 oggs share the same path+md5 as Amplified
    # (full diff, 0 differences), so it adds ZERO net-new (every file md5-dedups at stage 1). We ingest
    # sounds, not weather, so there is nothing to gain. Ref (credit only):
    # https://www.moddb.com/mods/stalker-anomaly/addons/dark-signal-amplified-soundscape-vanilla-edition
    {"name": "Soundscape", "licence": "free",
     "url": "https://www.moddb.com/mods/stalker-anomaly/addons/stalker-2-hoc-ambience-overhaul-for-anomaly",
     "path": "D:/Games/GAMMA/GAMMA/mods/3- Soundscape Overhaul - Solarint/gamedata"},
    {"name": "RETUNE457", "licence": "free",
     "url": "https://www.moddb.com/mods/stalker-anomaly/addons/retune-ambience-sounds",
     "path": "D:/Games/GAMMA/GAMMA/mods/457- RETUNE Ambiant Sounds - Aphrodite_child/gamedata"},
    {"name": "DarkSignal304", "licence": "free",
     "url": "https://www.moddb.com/mods/stalker-anomaly/addons/dark-signal-audioscape-weather-and-ambiance",
     "path": "D:/Games/GAMMA/GAMMA/mods/304- Dark Signal Weather and Ambiance Audio - Shrike/gamedata"},
    {"name": "myRETUNE", "licence": "free", "url": None,   # ref (add if known): myRETUNE AntaresWolverine 2.1 download page
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/audio/myRETUNE_AntaresWolverine_2.1/myRETUNE ambience sounds ver2.1/gamedata"},
    {"name": "RealDistantMutants", "licence": "free",
     "url": "https://www.moddb.com/mods/stalker-anomaly/addons/anomaly-real-distant-mutants-sounds-v10",
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/audio/Real Distant Mutants Sounds/gamedata"},
    {"name": "DSMutants", "licence": "free",
     "url": "https://www.moddb.com/mods/stalker-anomaly/addons/dark-signal-audioscape-mutants",
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/audio/276- Dark Signal Mutants Audio - Shrike/gamedata"},
    {"name": "AudioExpansion", "licence": "free",
     "url": "https://www.moddb.com/mods/stalker-anomaly/addons/audio-expansion",
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/audio/Audio Expansion/gamedata"},
    # Standalone STALKER builds (not moddb): pulled locally; ref links are origin/credit only.
    {"name": "DeadAir", "licence": "game", "url": None,        # ref (add if known): Dead Air build download
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/game_builds_for_sound/_unpacked/DeadAir"},
    {"name": "OGSE", "licence": "game",
     "url": "https://www.moddb.com/mods/old-good-stalker-evolution",
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/game_builds_for_sound/_unpacked/OGSE"},
    {"name": "Prosector", "licence": "game", "url": None,      # ref (add if known): Prosector build download
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/game_builds_for_sound/_unpacked/Prosector"},
    {"name": "Solyanka", "licence": "game", "url": None,       # ref (add if known): Solyanka build download
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/game_builds_for_sound/_unpacked/solyanka"},
    {"name": "NLC", "licence": "game", "url": None,            # ref (add if known): NLC build download
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/game_builds_for_sound/_unpacked/NLC"},
    {"name": "SoP", "licence": "game", "url": None,            # ref (add if known): SoP build download
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/game_builds_for_sound/_unpacked/sop"},
    {"name": "DarkSignal274", "licence": "free", "url": None,  # ref (add if known): 274- Dark Signal Audio Pack page
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/audio/274- Dark Signal Audio Pack - Shrike/gamedata"},
    {"name": "DarkSignal285", "licence": "free", "url": None,  # ref (add if known): 285- Dark Signal Blowout and Anomalies page
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/audio/285- Dark Signal Blowout and Anomalies Audio - Shrike/gamedata"},
    {"name": "AmbientExtended", "licence": "free",
     "url": "https://www.moddb.com/mods/stalker-anomaly/addons/ambient-extended-reworked",
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/audio/Ambient Extended Reworked/gamedata"},
    {"name": "ImmersiveAmbience", "licence": "free",
     "url": "https://www.moddb.com/mods/stalker-anomaly/addons/immersive-ambience-expansion",
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/audio/Immersive Ambience Expansion/gamedata"},
    # Original, granted directly by Shrike 2026-08-15, unreleased - there is NO public link (doc/licensing.md).
    {"name": "ShrikeInterior", "licence": "permission", "url": None,
     "path": "C:/Users/damian/Downloads/stalker_anomaly_mods/audio/Dark Signal Unused Interior - Shrike/gamedata"},
    # The base game (Anomaly 1.5.3 unpacked).
    {"name": "vanilla", "licence": "game", "url": None,
     "path": "D:/Games/GAMMA/Anomaly/tools/_unpacked"},
]


def mods():
    """(name, path) pairs in registry order - the exact shape and order the pipeline's MODS expects."""
    return [(s["name"], s["path"]) for s in SOURCES]


def by_name(name):
    for s in SOURCES:
        if s["name"] == name:
            return s
    return None


def check_licences():
    """Fail the build on any source whose licence is not cleared - never ship an uncleared source."""
    pending = [s["name"] for s in SOURCES if s.get("licence", "pending") == "pending"]
    if pending:
        raise SystemExit(f"licence gate: uncleared sources (licence=pending): {', '.join(pending)}")
