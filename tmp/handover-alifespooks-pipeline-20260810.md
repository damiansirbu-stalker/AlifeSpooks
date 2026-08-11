# Handover - AlifeSpooks pipeline + file-storage/mapping (2026-08-10)

Resume point: the director rework is committed and consistent (scoring, owned-loop veto, categories,
original-name deploy). The CONTENT PIPELINE is NOT settled: I flip-flopped on how we store files and
map them, left a WRONG uncommitted `merge.py` experiment, and did not finish. STOP and clarify the
pipeline WITH THE USER before touching it. Read this in FULL, run the session-start gate, then work.
DELETE this file once loaded and resumed (gitignored `tmp/`, never leave it behind).

I fucked up the pipeline part. I bounced between original-names, `N.ogg`, and pack-subdirs across the
session, and left `merge.py` in a broken half-state. The committed tree is fine; the uncommitted
`merge.py` is not. Do not build on it. See Current state and Corrections.

Written per `doc/standards/handover-protocol.md`. Registers are kept apart: FACTS are measured+cited,
DECISIONS are settled, HYPOTHESES are unproven, IDEAS are not chosen. Do not promote one to another.

---

## 1. How to work

- Follow `doc/standards/session-start-protocol.md` (load-and-prove) and the global
  `C:\Users\damian\.claude\CLAUDE.md` epistemic protocol. Open every answer `src: <type>; conf: <level>`.
- Any claim about engine/vanilla behavior is grepped in `stalker-resources/repos/sdk/xray-monolith/src`,
  `D:/Games/GAMMA/Anomaly/tools/_unpacked`, and `doc/library`, and cited `file:line`. No inference from names.
- Quote the user's authorizing words verbatim before any Edit. NEVER sync (user deploys). Validate ONE
  named mod at the end (`stalker-manager.sh validate-dev-mods AlifeSpooks`), confirm S+.
- The mod's term is SPOOK, never dread/horror as invented labels (dread is fine as plain English).

## 2. Load, then PROVE (session-start gate, no action before it)

Read IN FULL, tick each, then emit the proof-of-understanding gate BEFORE any proposal or edit:
- [ ] This file, fully, then delete it after resuming.
- [ ] Global `C:\Users\damian\.claude\CLAUDE.md` and the standards it links (writing, commit, todo, library).
- [ ] `doc/memory/memory-stalker-project.md` and the auto-memory index (`~/.claude/projects/.../memory/MEMORY.md`).
- [ ] `doc/standards/`: session-start-protocol, handover-protocol, code-standards, writing-standards,
      release-standards (readme.txt + changelog format), todo-standards.
- [ ] `AlifeSpooks/doc/architecture.md` IN FULL (it is the ORIGINAL model, enrich/restore/define + loop +
      clone-injects-placement; it is now STALE vs the code, but read it to understand what the pipeline was).
- [ ] Git history of the naming/pipeline: `git log --oneline -- gamedata/scripts/as_effect.script tools/merge.py`
      and read commits a7b67c4, 414b8db, e6a3861, 75d3a1d to see how the model got here.
- [ ] Code: `gamedata/scripts/as_effect.script` (the director + the owned-loop veto), `tools/merge.py`
      (the pipeline; `cmd_plan` dedup stages, `cmd_deploy`, `write_placement`, `cmd_provenance`, `cmd_ledger`),
      `configs/scripts/as_smart_lore.ltx`, `configs/environment/as_channel_layers.ltx`, `tools/provenance.tsv`.
- [ ] xlibs `xsmart.script` (get_declared_factions, is_base, get_actor_smart), `xcreature.script`
      (community, relation_to_actor, get_mutant_species), and how `game_relations.is_factions_enemies` is used.

## 3. Current state (committed vs uncommitted)

COMMITTED + PUSHED, AlifeSpooks `main` (consistent, S+, in-game testable):
- `a7b67c4` feat(spooks): runtime place/base/faction/safe scoring; drop dead lore, fix mutant tokens.
- `414b8db` build(spooks): deploy sounds under ORIGINAL names and paths, not N.ogg (`zs\<ch>\<orig path>.ogg`).
  This is the CURRENT deployed gamedata. provenance 1106 match / 0 mismatch, ledger UNUSED-DARK=0.
- `e6a3861` feat(spooks): own update_ambient and veto base copies of sounds we ship.
- `75d3a1d` feat(spooks): rebuild categories - real gates, one-shot weighting, revive creaks/wind.
COMMITTED + PUSHED, xlibs `main`: `e57de24` feat(xsmart): expose get_declared_factions as public.
COMMITTED + PUSHED, stalker-dev `main`: `d594ab0` docs(todo): record spook-director rework tasks (n113/n114/n115).

UNCOMMITTED (do NOT commit as-is; sort per Next steps):
- `tools/merge.py` - WRONG EXPERIMENT. It reverts the deploy to `N.ogg`, drops base-dedup, and adds a
  block-list emit, but was NEVER re-deployed and CONTRADICTS both the committed original-name gamedata AND
  the user's decision to keep original names. The `N.ogg` revert would also break the `e6a3861` veto (which
  matches by deployed filename). DISCARD it (`git checkout -- tools/merge.py`) and re-do per the DECISIONS.
- `doc/readme.txt` - rewritten to the systems-style current model (good, self-checks clean of semicolons),
  but a claim ("nothing your install already plays is shipped twice") conflicts with the base-dedup-drop
  decision. Reconcile before committing.
- `doc/architecture.md` - still the OLD model (enrich/loop/clone). NOT updated. Rewrite AFTER the pipeline
  is clarified.
- `doc/changelog/next.md` - old-model prose. The mod is UNRELEASED, so there is NO changelog to write.
  Also the shape is wrong: every other mod has a plain `doc/changelog` FILE; AlifeSpooks has a
  `doc/changelog/` DIRECTORY with `next.md`. Fix the shape or drop it until first release (user decision pending).
- `gamedata/configs/text/rus/ui_st_mcm_as.xml` - uncommitted from a prior session (RU MCM). windows-1251,
  xmlstarlet only.

## 4. FACTS (measured/cited this session)

- Deployed gamedata is original-name: `zs\<ch>\<orig path>.ogg` (e.g.
  `zs\as_out_mutants\ambient\soundscape\mutants\bloodsucker\distant_1.ogg`). PROOF: `git show 414b8db`,
  provenance self-verify 1106 match / 0 mismatch, ledger UNUSED-DARK=0 (run `python tools/merge.py provenance`).
- The base (Dark Signal Amplified) references its sounds by their ORIGINAL relative paths, case-inconsistent
  (`ambient\soundscape\spoops\Day_spoops\sound1`, `ambienturban_71` vs `AmbientUrban_45`). PROOF: its
  `gamedata/configs/environment/sound_channels.ltx` (`C:/Users/damian/Downloads/anomaly_audio_mods/Dark Signal Amplified Soundscape/...`).
  So a block-by-name must be case-insensitive.
- 83 of 1727 shipped stems are CROSS-MOD collisions: two source packs ship a DISTINCT recording (PCM-proved
  different) under the SAME source-relative path, both kept for variety. PROOF: measured over
  `tools/merged_channels.json` this session. Deployed by original path they clash and one overwrites the other.
- `provenance.tsv` is the origin MAPPING: columns `deployed, layer, group, orig_mod, orig_dir, orig_file,
  orig_channel, <settings>, orig_sections`. "Nothing loses its origin under the rename." Do NOT lose it.
- `merge.py cmd_plan` has three dedup stages: `dedup_pick` (per source channel, waveform), `_base_dedup`
  (vs the install's base index), `_cross_channel_dedup` (md5-exact across our channels). PROOF: `tools/merge.py:459-561`.
- The `e6a3861` veto: `as_effect` RemoveTimeEvent's vanilla `sound_ambient.update_ambient`
  (`sound_ambient.script:86`) and runs a faithful clone that skips any base sound whose normalized name is in
  the set built from OUR loaded channel sounds (strip `zs\<ch>\`, lowercase). PROOF: `as_effect.script` `_build_block`,
  `_base_reset`, `_base_fire`, `update_ambient_owned`, `_apply_owned`.

## 5. DECISIONS (settled; do not relitigate)

- KEEP ORIGINAL NAMES in the deploy. NOT `N.ogg`. (user, emphatic and repeated)
- Collisions are disambiguated with OUR OWN DIRECTORIES as a small exception (e.g. the `orig_mod` folder
  from the mapping for the clashing files), NOT a filename suffix and NOT `N.ogg`. (user)
- KEEP the provenance MAPPING to original mods; never lose or replace it. A runtime block list, if used, is
  DERIVED from it. (user)
- DROP base-dedup (stage 3). The runtime veto handles doubling; base-dedup deletes the very sounds we want
  the director to own. Ship the full curated dark corpus; veto blocks the base's copy at play time. (user, "agree drop 3")
- Scoring model (committed a7b67c4): every smart has a baseline (lore class or level_default); possible-hostility
  from the smart's declared factions vs the player's community (`game_relations.is_factions_enemies`), confirmed
  by live bodies; `is_base` amplifies; safe cutout = allies present + day + no threats; DREAD_FLOOR elsewhere. (settled)
- Categories (committed 75d3a1d): gates always / mutants / underground (`GetEvent("underground")`) /
  exterior_humans; one-shot weighting (no texture/loop split); creaks + wind revived; storm/rain dropped
  (weather is the base ambient's job). (user + settled)

## 6. THE THING TO CLARIFY (the mandate)

Clarify the PIPELINE and HOW WE STORE FILES AND MAPPINGS, with the user, before coding:
- File storage: original names, plus which own-directory scheme disambiguates the 83 cross-mod collisions
  (orig_mod folder for clashes only? for all? another scheme?). The user said original names + own dirs; the
  exact layout is not pinned.
- Mappings: `provenance.tsv` stays the origin record. Decide whether the runtime veto reads OUR deployed
  filenames (works while names are original, as e6a3861 does) or a separate provenance-derived block list.
- Then: drop base-dedup, re-run the pipeline, re-deploy, re-validate, and reconcile readme + architecture.
- Future scope the user flagged: they will add many ORIGINAL recordings and sounds mined from old STALKER
  games and other games, which have no meaningful "original path", so the storage scheme must scale to those.

## 7. HYPOTHESES / SUSPICIONS (unproven; each with its measurement)

- Dropping base-dedup grows the shipment by roughly the 3644 currently BASE-DUP-excluded (architecture.md
  "Numbers"). NOT re-measured; the real count comes from re-running `cmd_plan` without `_base_dedup`.
- With original names kept, the e6a3861 veto may not need a separate block list at all (deployed name ==
  orig path == what the base plays). MEASURE: after the storage scheme is fixed, confirm the strip-and-match
  still yields the base's orig path for every case including the disambiguated collisions.

## 8. IDEAS / VARIANTS (considered, not chosen)

- Collision disambiguation: (a) `orig_mod` folder for the 83 clashes only, 1644 pristine; (b) `orig_mod`
  folder for all; (c) drop the clash, keep one per path (loses distinct recordings). User leans (a)-style.
- Veto block source: (a) build from OUR deployed channel sounds at load (e6a3861 current); (b) a shipped
  provenance-derived path list (`as_blockdata.script` idea). Not chosen.

## 9. NEXT STEPS (in order)

1. Run the session-start gate (section 2). Emit the proof-of-understanding gate. No edits before it.
2. Clarify the pipeline + file storage + mappings WITH THE USER (section 6). Do not code first.
3. `git checkout -- tools/merge.py` to discard the wrong experiment (confirm no parallel session first).
4. Implement the agreed storage scheme (original names + own-dir collision handling) and the base-dedup drop
   in `merge.py`, re-run the pipeline (plan -> classify -> loudness -> deploy -> ledger -> provenance),
   re-validate S+, confirm provenance 0 mismatch and UNUSED-DARK accounting.
5. Reconcile `doc/readme.txt` (the base-dedup claim) and rewrite `doc/architecture.md` to the final model.
6. Decide the changelog shape (unreleased = none; fix `doc/changelog` dir vs file).

## 10. GOTCHAS

- The uncommitted `merge.py` is WRONG (N.ogg). Discard it; do not extend it.
- Committed A1 (original names) + A2 (veto reads deployed names) are CONSISTENT. Keep them consistent: any
  storage change must keep the veto's name-match valid, or move the veto to a provenance-derived list.
- RU MCM `ui_st_mcm_as.xml`: windows-1251, edit ONLY via xmlstarlet.
- `merge.py deploy` writes the REPO gamedata (a build), it is NOT a game sync. User syncs. Never sync.
- Re-running the pipeline needs the source packs on disk (confirmed present this session) and ffmpeg/Chromaprint.

## 11. CORRECTIONS

- I broke the pipeline file-storage part this session. I shipped 414b8db (original names, correct), then
  reverted `merge.py` to `N.ogg` (WRONG, rejected by the user), and proposed pack-subdirs the user rejected as
  framed. The settled direction is: original names + own-directory disambiguation for collisions + keep the
  provenance mapping + drop base-dedup. The uncommitted `merge.py` does not reflect this and must be redone.
- Earlier I wrote a feature-list into `doc/changelog/next.md`. Wrong: an unreleased mod has no changelog, and
  the mod description lives in `readme.txt`. Reverted.

## 12. REFERENCES

- AlifeSpooks: `gamedata/scripts/as_effect.script` (director + veto: `_score`, `_place`, `_possibly_hostile`,
  `_build_block`/`_base_reset`/`_base_fire`/`update_ambient_owned`/`_apply_owned`, CATEGORIES, `_gate_ok`),
  `tools/merge.py` (`cmd_plan`:459, dedup stages, `cmd_deploy`:1124, `write_placement`, `cmd_provenance`, `cmd_ledger`),
  `configs/scripts/as_smart_lore.ltx`, `configs/environment/as_channel_layers.ltx`, `tools/provenance.tsv`, `doc/architecture.md`.
- xlibs: `xsmart.script` (get_declared_factions, is_base, get_actor_smart), `xcreature.script`
  (community, relation_to_actor, get_mutant_species). Engine: `sound_ambient.script:86` (update_ambient),
  `level_weathers.script:128-129` (SetEvent underground).
- Commits: AlifeSpooks a7b67c4 / 414b8db / e6a3861 / 75d3a1d; xlibs e57de24; stalker-dev d594ab0.
- Standards: `doc/standards/session-start-protocol.md`, `handover-protocol.md`, `release-standards.md`,
  `code-standards.md`, `writing-standards.md`.

---

## PASTE-IN PROMPT (for the next session)

Read `AlifeSpooks/tmp/handover-alifespooks-pipeline-20260810.md` IN FULL and FIRST, then delete it once
loaded and resumed. Follow `doc/standards/session-start-protocol.md` (load-and-prove) and the global
CLAUDE.md epistemic protocol. Read the original `AlifeSpooks/doc/architecture.md`, the git history of
`as_effect.script` and `tools/merge.py`, the current state, and ALL my memory and standards before touching
anything. Focus: the director rework is committed and consistent, but the CONTENT PIPELINE is unsettled - we
must CLARIFY how we store files (original names + our own directories for collisions) and how we keep the
mappings (provenance), then drop base-dedup and re-run. The previous session broke this part and left a wrong
uncommitted `merge.py` to discard. Emit the proof-of-understanding gate (with `file:line` cites) BEFORE any
proposal or edit. Do NOT code first - clarify the pipeline with me. No skimming, no inference from names.
DELETE this file once loaded and resumed.
