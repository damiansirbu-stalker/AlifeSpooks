AlifeSpooks: dark horror ambience for STALKER Anomaly, by Damian
Version: next (xlibs required)
GitHub: https://github.com/damiansirbu-stalker/AlifeSpooks
Changelog: https://github.com/damiansirbu-stalker/AlifeSpooks/blob/main/doc/changelog
Russian / Na russkom: https://github.com/damiansirbu-stalker/AlifeSpooks/blob/main/doc/readme_ru.txt
Bugs, suggestions: https://github.com/damiansirbu-stalker/AlifeSpooks/issues

Alife Collection:
AlifeBalance: https://www.moddb.com/mods/stalker-anomaly/addons/alifebalance
AlifeDiegetic: https://www.moddb.com/mods/stalker-anomaly/addons/diegetic-audio-control-100
AlifeGuard: https://www.moddb.com/mods/stalker-anomaly/addons/alifeguard-1001
AlifePlus: https://www.moddb.com/mods/stalker-anomaly/addons/alifeplus-v1-0-01
AlifeSpooks: https://github.com/damiansirbu-stalker/AlifeSpooks
AlifeTactics: https://www.moddb.com/mods/stalker-anomaly/addons/alifetactics

Reset MCM settings to defaults after updating.

The Zone used to be frightening. Modern soundscape mods sharpened its realism and stripped the horror out in the trade. AlifeSpooks puts it back.

It is a dread director. It reads where you stand and who is near, scores the dread of the place, and plays curated horror one-shots to match.
Nothing is a random timer and nothing is scripted.
The soundscape follows the real state of the game around you, the way the rest of the Alife Collection reads state and decides rather than rolls dice.

The mod is three things. A director reads the Zone and plays to it. A veto keeps it from ever doubling the base ambience. A measured pipeline builds its sound library.
It needs xlibs, the library that plays its sounds. Without xlibs the mod is inert.


1. The director

The director is the core. It scores the dread of your surroundings, and the score decides which sounds are eligible, how close they play, and how loud.
A friendly base in daylight is quiet. A psi lab with a mutant near at night is loud. Most of the Zone sits in between.
The dread is one plain sum, lore plus who's around plus indoor plus time, with no multiplier and no floor.

Lore. The smart terrain you stand in is looked up in a hand-curated table taken to canon.
That covers the psi zones (Yantar, Radar, Red Forest, the reactor), the labs, the dens, the ruined cities, and the eerie wilds.
A place not in the table falls to a per-level baseline. This is the dread a place carries on its own, before anything happens.

Who's around. One reading of your company: alone, among allies, near enemies, near mutants, or a mix.
Your own people are the only thing that calms you. Alone or with a threat near, the Zone stays uneasy on its own. Enemy ground counts as hostile even when the base sits empty.
Safety is a live fact, not a spot marked safe on a list, so an emptied or infiltrated base at night is not safe.
Faction hostility is read from the game's own relations, so a base is friendly or hostile by the faction you play, not a fixed assumption that you are a loner.
It is not a body count or a threat meter, only what kind of company you keep.

Indoor. Enclosed spaces feel scarier than the open. A real roof-and-wall raycast or a surge shelter decides it.

Time. A few steps through the day: calm by day, a nudge at dusk and dawn, up at night, most in the dead of night.

Your own people settle the unease, so a calm place with allies falls quiet, and a truly grim place still carries its dread.
It is one plain sum with no artificial floor and no cutout, so the Zone is never dead quiet where it should not be, and never forced silent where it should not be either.

The palette. The sounds are grouped into categories, each with the condition it fires under and a minimum spacing, so a scream stays rare against the wind.
Spooks, screams, and dark drones play wherever the dread is up. Growls need a real mutant near.
Tunnel and machine sound plays on an actual underground level, read from the engine's own underground flag, not in a surface building.
Gunfire plays outdoors where humans are present, because someone has to fire the shot. Wind, creaks, and eerie wildlife play everywhere as texture.
The loud scares stay rare and spaced, and no call plays twice in a row.

Each one-shot is positioned around you with the game's own ambient geometry, a little closer at peak dread, and left to the engine's own distance rolloff, so a near sound is full and a far one fades.
A long horror drone or a psy bed plays as a spaced one-shot, never a continuous loop.


2. The veto

The mod never doubles the base ambience. If you also run a soundscape pack it drew from, that pack's ambient plays the same sounds.
AlifeSpooks removes its own sounds from the base's ambient channels, so only its curated version plays, under its director.

It does this statically, at config load, with a generated overlay.
The overlay strips each of the mod's sounds out of every base channel that lists it, matched by the sound's own audio, so it catches the copy whichever pack reships it.
It leaves every other base sound untouched. It is a config change, not a runtime loop, so it is deterministic and cannot be lost to another script.
It can never over-reach. It removes only the exact sounds the mod plays, never a folder, never a channel, never a wind bed or a creature call it does not carry.
No collision and no doubled density, over GAMMA, vanilla, or any soundscape base. The base's own atmosphere plays exactly as it always did.


3. The source and the measured pipeline

The audio is built by a reproducible, measured pipeline, one command end to end, not dumped in. Every sound is analyzed before it goes in.
ffmpeg reads its spectral centroid and flatness, its crest factor, and its integrated loudness in EBU R128 LUFS. ffprobe reads its duration, sample rate, and codec.
Each pack's folders are mapped to horror categories by hand, and every file in them is pulled, so nothing the pack buries goes missed.
A sound too long for a one-shot is dropped, and the long radio-signal bed is sliced into short pieces, so nothing overlaps itself.
Each file's loudness is leveled to a common target by editing its ogg gain field, losslessly, so the corpus is even without a single re-encode.

Identity is decided by the waveform, in three stages, cheapest first, so the expensive test runs only on the pairs the cheap ones flag. An exact md5 hash collapses byte-identical reships.
A Chromaprint acoustic fingerprint proposes the re-encoded copies the hash misses, but its same-versus-distinct ranges overlap, so it only proposes and never decides.
A PCM cross-correlation decides. It decodes both files, aligns them by envelope, and correlates over the overlap, where a re-encode scores near 1.0 and a different sound near 0.
Files merge only under complete linkage, so a similarity chain never collapses two distinct recordings, and variety is never lost. This runs among the source packs only.
The mod never drops a sound because your install already plays it. It carries the full curated dark corpus and removes the base copy at load instead.

Every kept sound is redistributed byte for byte, carrying its own X-Ray volume and distance in its ogg comment.
A source that lacks that metadata is given it losslessly, the median of its category band, so only the comment header changes and the audio bytes stay identical.
A fitness gate keeps 44.1 kHz vorbis, the X-Ray standard, and accounts anything dropped. A ledger proves no net-new dark sound is missed.
A provenance record maps every carried sound back to its origin mod, folder, name, and settings, and self-verifies by audio hash.
Nothing loses its origin, even though the files are organized into the mod's own categories.

It reads cheap signals every few seconds, never per frame, and caches them, so the cost is a slow timer whatever plays on screen.


MCM:
The MCM has three tabs. Atmosphere holds an overall volume, rarity, distance, and a per-category volume slider for each kind of sound.
The categories are drone, spook, scream, growl, machine, gunfire, underground, creak, wind, and wildlife, so you can turn screams down and underground up on their own.
Visuals toggles the screen distortion at peak dread. Development holds the trace level, a log flush, the debug HUD, and a reset-to-defaults button.
The in-game HUD reads out the current dread, each term that fed it, what is playing, and what the base ambience is playing, so you can see exactly why a place sounds the way it does.

Requirements:
Anomaly 1.5.3
xlibs (plays the sounds, https://www.moddb.com/mods/stalker-anomaly/addons/xlibs-1001)
MCM (for the settings and the trace)

Install (MO2):
1. Install xlibs
2. Install this mod
3. Load order does not matter
4. Configure via MCM

Uninstall (MO2):
Disable or remove in MO2.

Performance:
Performance comes first, ahead of any feature. AlifeSpooks reads its signals every few seconds and caches them, never per frame, and its audio is byte for byte with no engine-bed cost.
When a feature cannot fit that budget it is reworked, replaced, or removed with an X-Ray engine modification rather than allowed to slow the game.

Compatibility:
Built for GAMMA and the Dark Signal soundscape base, and it runs on vanilla Anomaly and any soundscape mod.
Because it removes only its own sounds from the base channels and adds nothing, it never doubles or collides with the base ambience, whatever pack you run.
You can install or remove it mid-save. Weather sound stays the base ambience's job, AlifeSpooks adds no storm or rain.

Credits:
The content is drawn from these community packs, with thanks to their authors.
Dark Signal Weather and Ambiance, by Shrike.
Dark Signal Amplified Soundscape, by Shrike.
Soundscape Overhaul, by Solarint.
RETUNE Ambient Sounds, by Aphrodite_child.
Real Distant Mutants Sounds, distant creature calls, from moddb.
Audio Expansion, underground and surface spook, from moddb.
Used under the terms on each source page. Only the selected audio is redistributed, with attribution. If an author asks for removal, the pack is dropped from the build.

Usage and License:
Modpacks are allowed and encouraged. Keep the readme and license files.
Addons, patches, and integrations are allowed. Credit "AlifeSpooks by Damian Sirbu" visibly on your mod page.
You may not reproduce the implementation in other software, even with credit.
The full license is in the LICENSE file and on GitHub.

Issues and suggestions:
Open a report at https://github.com/damiansirbu-stalker/AlifeSpooks/issues/new/choose, or ask on the GAMMA, EFP, Anomaly, and Zona Discord servers.
Read this readme and the MCM options first. Set the MCM log level to DEBUG, reproduce, then back to WARN, and include the debug log with your report.
