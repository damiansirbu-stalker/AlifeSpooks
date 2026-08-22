AlifeSpooks: dark horror ambience for STALKER Anomaly, by Damian
Version: next (xlibs required)
GitHub: https://github.com/damiansirbu-stalker/AlifeSpooks
Changelog: https://github.com/damiansirbu-stalker/AlifeSpooks/blob/main/doc/changelog
Read it in Russian / Na russkom: https://github.com/damiansirbu-stalker/AlifeSpooks/blob/main/doc/readme_ru.txt
Report bugs and suggestions: https://github.com/damiansirbu-stalker/AlifeSpooks/issues

Alife Collection:
AlifeBalance: https://www.moddb.com/mods/stalker-anomaly/addons/alifebalance
AlifeDiegetic: https://www.moddb.com/mods/stalker-anomaly/addons/diegetic-audio-control-100
AlifeGuard: https://www.moddb.com/mods/stalker-anomaly/addons/alifeguard-1001
AlifePlus: https://www.moddb.com/mods/stalker-anomaly/addons/alifeplus-v1-0-01
AlifeSpooks: https://github.com/damiansirbu-stalker/AlifeSpooks
AlifeTactics: https://www.moddb.com/mods/stalker-anomaly/addons/alifetactics

Reset MCM settings to defaults after updating.

The Zone used to be frightening.
Modern soundscape mods traded that dread for realism.
AlifeSpooks is my attempt to put the fear back without giving up the fidelity.

It is a dread director, driven by where you stand and who is near. It answers the dread of the place with curated horror one-shots.
No random timers, no scripts. The soundscape follows the real state of the game around you.
Some of its horror is interior audio Shrike made for Dark Signal and never released, given straight to this mod.

AlifeAmbience is its companion.
AlifeSpooks plays the horror and vetoes it from the base channels. AlifeAmbience owns the living nature-and-weather bed it leaves alone.
Run both and the Zone is real and frightening at once.

Three parts.
A director reads the Zone and plays to it.
A veto keeps it from doubling the base ambience.
A measured pipeline builds the sound library.
It needs xlibs to play the sounds. Without xlibs it is inert.


1. The director

Two things drive it.
WHERE you stand decides which sounds can play.
How much DREAD the place carries decides how close, how often, and which of them play.
A base in daylight is silent. A lab with a mutant near at night is loud and close. Most of the Zone sits between.

Where you are, checked in order.
Each level has a curated list of what belongs on it, traced from the source packs.
A lab plays facility and machine sound. A swamp plays its own mutant atmosphere. A wild forest never plays the radio signal.
A base near, marked by a live service NPC, cancels everything and goes silent, whatever faction owns it.
The enclosure filters the rest. Outdoor never plays doors or machinery. An interior never plays leaves or wind.

Dread itself is one plain sum, no multiplier and no floor.
It adds the level's baseline, how enclosed you are, the hour, and the single scariest thing near, then subtracts your own people around.
The baseline is the dread a place carries alone, grim in the psi north and the labs, mundane in the fields.
The scariest thing near is one reading, never a body count. A man and a monster of the same strength weigh the same.
True isolation weighs a little on its own.
Allies near are the only thing that calms you, so a place with your people falls quiet while a grim empty one still carries its dread.
Dread places a sound closer and fires it more often as it rises.
It never changes the sound's own level, only how near it plays, and never so far that it falls silent.

The palette.
Sounds fall into categories, each playing only where it fits and only when its condition holds.
Spooks, screams, and dark drones play wherever the map allows.
Mutant calls need a mutant present. Gunfire needs a person. The radio signal needs a signal source nearby.
Wind, foliage, and eerie wildlife are outdoor texture. Doors, machinery, drips, and facility sound belong indoors and underground.
Each category rotates so a scare stays rare against the texture and no call plays twice in a row.
Dread also chooses within a category.
By default a sound plays at every dread level.
You can hold a calm sound to quiet scenes and a scare to tense ones, so the palette shifts as the dread climbs.
That tuning is per-sound, hand-set, and separate from the audio, so it survives every rebuild of the library.

The director places each one-shot in 3D around and above you, at the distance its own author chose.
It uses the same placement the game's ambient system uses, so a sound plays as it did in the mod it came from.
A sound meant to come from overhead still does.
Every sound is mono, the only form the engine places in 3D, so nothing sticks flat at your ear.
A long drone or the radio signal plays as a spaced one-shot, never a loop.


2. The veto

If you also run a soundscape pack it drew from, that pack's ambient plays the same sounds.
AlifeSpooks removes its own sounds from the base's ambient channels, so only its curated version plays, under its director.
It does this statically at config load, with a generated overlay that strips each of the mod's sounds out of every base channel that lists it, at the path each source pack files it under.
A sound can ship in more than one pack. The copies include exact reships and re-encodes. It removes every one. Whichever pack you run, the base loses its version.
The base keeps everything else it plays.
It removes exact sounds, never a folder, never a channel, never a wind bed or creature call the mod does not carry.
It is one config change at load, not a runtime loop, so it costs nothing while you play and no other script can strip it.
GAMMA, vanilla, and the Dark Signal packs each keep their own atmosphere.


3. The source and the measured pipeline

Measurement drives every choice here, not taste.
The build is a reproducible pipeline, one command end to end.
It measures every sound before it goes in.
ffmpeg reads its spectral centroid, flatness, crest factor, integrated loudness in EBU R128 LUFS. ffprobe reads its duration, sample rate, codec.
Each pack's folders map to horror categories by hand, and the build pulls every file in them, so it misses nothing the pack buries.
The build drops a sound too long for a one-shot. It slices the long radio-signal bed into short pieces.
Each file keeps its author's own loudness, the X-Ray gain set in the ogg comment, written back unchanged. No leveling.
The authored levels are tight and field-tested in the source mods, so the corpus already plays even.
Dread comes from where the director places a sound, not from re-leveling one file against the next.
The gain is a number in the header, not the audio, so nothing is re-encoded.

Identity is the waveform, decided in three stages, cheapest first.
An md5 hash collapses byte-identical reships.
A Chromaprint fingerprint proposes the re-encoded copies the hash misses, but its ranges overlap, so it only proposes.
A PCM cross-correlation decides. It decodes both files, aligns them by envelope, then correlates over the overlap. A re-encode scores near 1.0, a different sound near 0.
Files merge only under complete linkage, so a similarity chain never collapses two real recordings and variety holds.
This runs among the source packs only.
The mod never drops a sound because your install already plays it. It carries the full corpus and removes the base copy at load instead.

Mono ships byte for byte, audio untouched, carrying its author's volume and distance band in the ogg comment.
Stereo is the one exception. The engine cannot place it in 3D, so the build folds it to mono and then writes the comment, the author's values captured before the fold.
A file that lacks that metadata gets it losslessly, the median of its category band, so only the header changes.
Most of this corpus never played where it came from.
Their packs carried two thirds of the files but wired them into no channel, so their own schedulers never played them.
Most of the rest carry an unset engine distance field that silences a sound more than a few meters away.
The build corrects that one field to the game's own far-ambience standard.
Thousands of sounds that existed only as files on disk now play in the world, at their author's loudness, for the first time.
A fitness gate keeps 44.1 kHz vorbis, the X-Ray standard, and accounts anything dropped.
A ledger proves the build misses no dark sound.
A provenance record maps every shipped sound back to its origin mod, folder, and name, self-verified by audio hash. Nothing loses its origin.
The director reads cheap signals every few seconds, never per frame, then caches them. The cost stays a slow timer whatever is on screen.


MCM:
Three tabs.
Atmosphere holds one master volume for the mod's sounds plus rarity.
That volume also balances the horror against your base ambience.
The mod plays each sound at its author's loudness and never touches the base.
So if your soundscape mod sits louder or quieter, this slider sets the dread against it.
There are no per-category sliders.
Visuals toggles the screen distortion at peak dread.
Development holds the trace level, a log flush, the debug HUD, and a reset button.
The in-game HUD reads out the current dread, each term that fed it, what is playing, and what the base ambience is playing, so you can see why a place sounds the way it does.

Requirements:
Anomaly 1.5.3
xlibs (plays the sounds, https://www.moddb.com/mods/stalker-anomaly/addons/xlibs-1001)
MCM (shows the settings and the trace)

Install (MO2):
1. Install xlibs
2. Install this mod
3. Load order does not matter
4. Configure via MCM

Uninstall (MO2):
Disable or remove in MO2.

Performance:
Performance comes first, ahead of any feature.
AlifeSpooks reads its signals every few seconds and caches them, never per frame. Its audio is byte for byte with no engine-bed cost.
A feature that cannot fit that budget changes, or moves into an X-Ray engine modification, before it slows the game.

Compatibility:
It runs on vanilla Anomaly, on GAMMA, and alongside any soundscape mod.
It removes only its own sounds from the base channels and adds nothing. It never doubles or collides with the base ambience.
It runs as a self-contained layer. It plays its own sounds through its own director, so it never fights a soundscape mod.
Its removal only takes sounds out, so it can never empty or break a base channel. It replays whatever base ambience wins, so those beds keep sounding.
Its own sounds play at their authors' loudness and distances, so the horror sits within the base mix rather than over it.
The master volume balances the two when a base runs unusually loud or quiet.
Tested against Anomaly 1.5.3 and GAMMA (installer definition 920, with Soundscape Overhaul and Dark Signal Weather and Ambiance active).
Tested with every source pack listed under Credits below.
Its Vanilla-weather edition is the same audio, credited under Amplified Soundscape.
You can install or remove it mid-save. Weather sound stays the base ambience's job. AlifeSpooks adds no storm or rain.

Credits:
Most of the sounds come from the original S.T.A.L.K.E.R. games and the standalone builds that carry and rework that audio.
Those builds: Solyanka (NS OGSR), Dead Air, OGSE, Prosector, NLC, OLR, Lost Alpha.
The rest is dark ambience from community soundscape packs, with thanks to their authors.
Shrike made the Dark Signal family and Amplified Soundscape. Solarint made Soundscape Overhaul.
Aphrodite_child and myRETUNE Antares made RETUNE. AniHVX made Audio Expansion.
Txiku made Ambient Extended. Kutee made Immersive Ambience Expansion. Real Distant Mutants Sounds rounds out the set.
Shrike also gave unreleased interior audio he made for Dark Signal and never released, exclusive to this mod.
Each source carries a free license, or its author gave permission for my mods, not tied to any one mod.
I credit every author above. I include only selected audio. If an author does not want their work included, I remove it.
licensing.md records each source's license and the granting author's permission. I include nothing without a free license or the author's consent.

Usage and License:
Modpacks are welcome. Keep the readme and license files.
Addons, patches, and integrations are fine. Credit "AlifeSpooks by Damian Sirbu" visibly on your mod page.
You may not reproduce the implementation in other software, even with credit.
The full license is in the LICENSE file and on GitHub.

Issues and suggestions:
Open a report at https://github.com/damiansirbu-stalker/AlifeSpooks/issues/new/choose, or ask on the GAMMA, EFP, Anomaly, and Zona Discord servers.
Read this readme and the MCM options first. Set the MCM log level to DEBUG. Reproduce the issue. Set it back to WARN. Include the debug log with your report.
