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
Part of its horror is unreleased Dark Signal audio, interior sound Shrike made and never released, given straight to this mod.

The mod is three things. A director reads the Zone and plays to it. A veto keeps it from ever doubling the base ambience. A measured pipeline builds its sound library.
It needs xlibs, the library that plays its sounds. Without xlibs the mod is inert.


1. The director

The director is the core. It reads where you are and plays to it. Two things drive it: WHERE you stand decides which sounds can play, and how much DREAD the place carries decides how close and how often they play.
A base in daylight is silent. A lab with a mutant near at night is loud and close. Most of the Zone sits in between.

Where you are. Selection is geography, checked in order.
The map you are on has a curated list of what belongs there, traced from the source packs, so a lab level plays facility and machine sound, a swamp plays its own mutant atmosphere, and a wild forest never plays the radio signal.
A base near, spotted by a live trader, medic, or mechanic, cancels everything: a base is a safe hub and goes silent, whatever faction owns it.
Outdoor, indoor, underground, or a lab then filters the rest, so the open never plays doors or machinery and an interior never plays leaves or wind.

How much dread. Dread is one plain sum, with no multiplier and no floor: the level's own baseline, plus how enclosed you are, plus the hour, plus the single scariest thing near, minus your own people around.
The level baseline is the dread a place carries on its own, grim in the psi north and the labs, mundane in the fields.
The scariest thing near is one reading and never a body count, and a man is weighed like a monster by its strength: the strongest one near weighs most, a weaker one less, and being truly alone weighs a little on its own.
Allies near are the only thing that calms you, so a place with your people falls quiet while a grim empty place still carries its dread.
Dread drives how close a sound is placed and how often it fires. A calm place puts them far and faint, a scary one brings them close and loud. It never changes the sound's own level, only how near it plays, and never so far that it falls silent.

The palette. The sounds are grouped into categories, each playing only where it fits and only when its condition is met.
Spooks, screams, and dark drones play wherever the map allows. A mutant category needs a real mutant present, gunfire needs a person present, and the radio signal plays only where a signal source makes sense.
Wind, foliage, and eerie wildlife are outdoor texture, while doors, machinery, drips, and facility sound belong indoors and underground.
Every category rotates so a scare stays rare against the texture, and no call plays twice in a row.

Each one-shot is placed in 3D around and above you, in the sound's own distance band from the pack it came from: far and faint when the place is calm, close and loud when dread peaks, with a hard floor so it never goes silent and a ceiling so a close one never blares. A sound the author meant to come from overhead still comes from overhead. Nothing is a flat 2D beep at a fixed spot.
A long horror drone or the radio signal plays as a spaced one-shot, never a continuous loop.


2. The veto

The mod never doubles the base ambience. If you also run a soundscape pack it drew from, that pack's ambient plays the same sounds.
AlifeSpooks removes its own sounds from the base's ambient channels, so only its curated version plays, under its director.

It does this statically, at config load, with a generated overlay.
The overlay strips each of the mod's sounds out of every base channel that lists it, matched by the sound's own audio, so it catches the copy whichever pack reships it.
It leaves every other base sound untouched. It is a config change, not a runtime loop, so it is deterministic and cannot be lost to another script.
It can never over-reach. It removes only the exact sounds the mod plays, never a folder, never a channel, never a wind bed or a creature call it does not carry.
No collision and no doubled density over the soundscape bases it is built against: GAMMA, vanilla, and the Dark Signal packs. The base's own atmosphere plays exactly as it always did.


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
A provenance record maps every carried sound back to its origin mod, folder, and name, and self-verifies by audio hash.
Nothing loses its origin, even though the files are organized into the mod's own categories.

It reads cheap signals every few seconds, never per frame, and caches them, so the cost is a slow timer whatever plays on screen.


MCM:
The MCM has three tabs. Atmosphere holds one master volume for the mod's sounds, plus rarity and distance.
There are no per-category sliders: the director mixes every kind of sound off the single master.
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
Because it removes only its own sounds from the base channels and adds nothing, it does not double or collide with the base ambience over GAMMA, vanilla, and the soundscape packs it is built against.
Tested against Anomaly 1.5.3 and GAMMA (installer definition 920, with Soundscape Overhaul and Dark Signal Weather and Ambiance active), and with the soundscape and ambient packs it draws from: Dark Signal Amplified Soundscape, the Dark Signal Audio, Mutants, and Blowout and Anomalies packs, RETUNE Ambient Sounds, myRETUNE Antares 2.1, Audio Expansion, Ambient Extended Reworked, Immersive Ambience Expansion, and Real Distant Mutants Sounds. Its Vanilla-weather edition is the same audio, credited under Amplified Soundscape.
You can install or remove it mid-save. Weather sound stays the base ambience's job, AlifeSpooks adds no storm or rain.

Credits:
Most of the sounds come from the original S.T.A.L.K.E.R. games and from the standalone builds that carry and rework their audio: Solyanka (NS OGSR), Dead Air, OGSE, Prosector, NLC, and OLR.
The rest is dark ambience from community soundscape packs, with thanks to their authors: the Dark Signal family and Amplified Soundscape by Shrike, Soundscape Overhaul by Solarint, RETUNE by Aphrodite_child and myRETUNE Antares, Audio Expansion by AniHVX, Ambient Extended by Txiku, Immersive Ambience Expansion by Kutee, and Real Distant Mutants Sounds.
Shrike also gave unreleased interior audio he made for Dark Signal and never released, exclusive to this mod.
Every author is credited above. Only selected audio is redistributed. If an author does not want their work included, it is removed from the build.
Each source's license and the granting author's permission are recorded in licensing.md; nothing ships without a free license or the author's consent.

Usage and License:
Modpacks are allowed and encouraged. Keep the readme and license files.
Addons, patches, and integrations are allowed. Credit "AlifeSpooks by Damian Sirbu" visibly on your mod page.
You may not reproduce the implementation in other software, even with credit.
The full license is in the LICENSE file and on GitHub.

Issues and suggestions:
Open a report at https://github.com/damiansirbu-stalker/AlifeSpooks/issues/new/choose, or ask on the GAMMA, EFP, Anomaly, and Zona Discord servers.
Read this readme and the MCM options first. Set the MCM log level to DEBUG, reproduce, then back to WARN, and include the debug log with your report.
