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

The Zone used to be frightening. Modern soundscape mods sharpened its realism and, in the trade, stripped the horror out. AlifeSpooks puts it back.

It is a dread director. It reads where you stand and who is near, then plays curated horror one-shots to match. Nothing is a random timer and nothing is scripted. The soundscape follows the real state of the game around you, the same way the rest of the Alife Collection reads state and decides rather than rolling dice.

Effects:
- Dread reads the place. A bloodsucker den, a lab, the psi fields of the north, and a ruined city each sound like what they are, before anything happens.
- Dread reads the people. Enemy ground and hostile squads raise it, a mutant near raises it and lets the growls in, your own people at a held base in daylight bring quiet.
- Safety is a live fact. Your allies are here now, it is not a spot marked safe on a list, so an emptied or infiltrated base at night is not safe.
- Faction hostility is read from the game's own relations, so a base is friendly or hostile by the faction you play, not a fixed assumption that you are a loner.
- The loud scares stay rare and spaced, and no call plays twice in a row.
- The mod plays its own version of a sound and mutes the modpack's copy, so nothing you install already carries is ever heard twice at once.

Everything is faithful, measured, and fast:
- The mod plays its own sounds and adds no ambient channel and edits no ambient file. It owns only the one dynamic-ambient function every scripted ambient sound already passes through, and only to mute the base's copy of a sound it also ships.
- Every sound is real, drawn from community soundscape packs, measured before it goes in, and deduplicated by its waveform, so no two shipped files are the same recording and no variety is lost.
- Every sound keeps its own volume and distance in its ogg, and its origin mod, folder, and name are recorded, so nothing is lost even though the files are organized into the mod's own categories.
- It reads cheap signals every few seconds, never per frame, and caches them. The cost is a slow timer whatever plays on screen.
- It requires xlibs, the library that plays its sounds. Without xlibs the mod is inert.

The dread director:
The director is the core. It scores the dread of your surroundings from four reads, and the score decides which sounds are eligible, how often they fire, how close they play, and how loud. A safe place is silent, a psi lab with a mutant near at night is loud, and most of the Zone sits in between with a low, uneasy floor.

- Place. The smart terrain you stand in is looked up in a hand-curated lore table taken to canon: the psi zones (Yantar, Radar, Red Forest, the reactor), the labs, the mutant dens, the ruined cities, the eerie wilds. A smart not in the table falls to a per-level baseline. This is the dread a place carries on its own, empty and quiet.
- Faction. A base's owning faction is read and checked against your own community through the game's relation system. Allied ground reads as a refuge, enemy ground reads as hostile, and it is correct whether you play a loner, Duty, a bandit, or Monolith. It is not a hardcoded "safe if you are a loner" list.
- Presence. The live creatures around you, read from the online set within range, not a smart's roster: allied and enemy humans, and horror-tier mutants. Enemies raise the dread, a real mutant raises it and opens the growl category, allies ease it. Trash-tier mutants never count.
- Safety. The one cutout to silence. Your own people present, in daylight, with no threat near, drops the dread to calm. Everything off that cutout keeps at least a low murmur, so a friendly base full of allies is the only true refuge and the Zone is never dead quiet where it should not be.

The palette:
The sounds are grouped into categories, each with the condition it fires under and a minimum spacing so a scream stays rare against the wind. Spooks, screams, and dark drones play wherever the dread is up. Growls need a real mutant near. Tunnel and machine sound plays on an actual underground level, read from the engine's own underground flag, not in a surface building. Gunfire plays outdoors where humans are present, because someone has to fire the shot. Wind, creaks, and eerie wildlife play everywhere as texture.

It plays its own sounds and never adds a channel:
The mod ships its sounds in its own directories and plays them itself, as positioned one-shots. It defines no ambient channel and injects nothing into the base ambient. A long horror drone or a psy bed plays as a spaced one-shot, not a continuous loop.

It never doubles the base. If you also run a soundscape pack the mod pulled from, that pack plays the same spook sounds. The director owns the game's dynamic-ambient loop and runs a faithful clone of it, with one change: any sound the mod itself ships is muted in the base loop, matched by the sound's original path, so the mod's curated version plays under its director instead of the modpack's copy playing alongside it. The base's other ambient plays untouched. The mod suppresses a base play, it never injects one. The result is no collision and no doubled density, over GAMMA, vanilla, or any soundscape base.

The measured pipeline:
The audio is built by a reproducible, measured pipeline, one command end to end, not dumped in. Every sound is analyzed with signal-analysis tools before it goes in. ffmpeg reads its spectral centroid and flatness, its crest factor, and its integrated loudness in EBU R128 LUFS. ffprobe reads its duration, sample rate, and codec. The measured duration sets how far apart the sound may fire, so a long sound never overlaps itself.

Identity is decided by the waveform, in three stages, cheapest first so the expensive test runs only on the pairs the cheap ones flag. An exact md5 hash collapses byte-identical reships. A Chromaprint acoustic fingerprint (fpcalc) is stable across bitrate and codec, so it proposes the re-encoded copies the hash misses, but its same-versus-distinct ranges overlap, so it only proposes and never decides. A PCM cross-correlation decides: it decodes both files, aligns them by envelope, and correlates over the overlap, where a re-encode scores near 1.0 and a genuinely different sound near 0. Files merge only under complete linkage, so a similarity chain never collapses two distinct sounds and variety is never lost. This runs among the source packs only. The mod never deletes a sound because your install already plays it. It ships the full curated dark corpus and mutes the base copy at play instead.

Every kept sound ships byte for byte, carrying its own X-Ray volume and distance in its ogg comment. A source that lacks that metadata is given it losslessly, the median of its category band, so only the comment header changes and the audio bytes stay identical. A fitness gate keeps 44.1 kHz vorbis, the X-Ray standard, and accounts anything dropped. A ledger proves no net-new dark sound is missed. A provenance record maps every shipped sound back to its origin mod, folder, name, and settings, and self-verifies by audio hash.

MCM:
Three tabs. Atmosphere holds an overall volume, spook sensitivity, rarity, distance, and a per-category volume slider for each kind of spook (drone, spook, scream, growl, machine, gunfire, underground, creak, wind, wildlife), so you can turn screams down and underground up on their own. Visuals toggles the screen distortion at peak dread. Development holds the trace level, a log flush, the debug HUD, and a reset-to-defaults button. The in-game trace logs every sound played and every term of the dread score, so you can read exactly why a place sounds the way it does.

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
Performance comes first, ahead of any feature. AlifeSpooks reads its signals every few seconds and caches them, never per frame, and it ships audio byte for byte with no engine-bed cost. When a feature cannot fit that budget it is reworked, replaced, or removed with an X-Ray engine modification rather than allowed to slow the game.

Compatibility:
Built for GAMMA and the Dark Signal soundscape base, and it runs on vanilla Anomaly and any soundscape mod. Because it plays its own sounds and mutes only its own in the base loop, it never doubles or collides with the base ambient, whatever pack you run. Installing or removing mid-save works. Weather sound stays the base ambient's job, AlifeSpooks adds no storm or rain.

Credits:
The content is drawn from these community packs, with thanks to their authors:
  Dark Signal Weather and Ambiance   - Shrike
  Dark Signal Amplified Soundscape   - Shrike
  Soundscape Overhaul                - Solarint
  RETUNE Ambient Sounds              - Aphrodite_child
  Real Distant Mutants Sounds        - moddb, distant creature calls
  Audio Expansion                    - moddb, underground and surface dread
Used under the terms on each source page. Only the selected audio is redistributed, with attribution. If an author requests removal, their pack is dropped from the build.

Usage and License:
  Modpacks: allowed and encouraged. Keep the readme and license files.
  Addons, patches, integrations: allowed. Credit "AlifeSpooks by Damian Sirbu" visibly on your mod page.
  Reproducing the implementation in other software: not allowed, even with credit.
  Full license in LICENSE file and on GitHub.

Reporting issues and suggestions:
Open a report at https://github.com/damiansirbu-stalker/AlifeSpooks/issues/new/choose, or ask on the GAMMA, EFP, Anomaly, and Zona Discord servers. Read this readme and the MCM options first. Set the MCM log level to DEBUG, reproduce, then back to WARN, and include the debug log with your report.
