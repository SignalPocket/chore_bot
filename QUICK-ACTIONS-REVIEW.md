# Sprig 2.3.0 candidate

Prepared from SignalPocket/chore_bot main commit 00d7e1dd0a1df4973b239886fbc03703e5ee010b.

Manage → Archive chore opens the active archive selector directly. Needs attention provides Claim beside each current chore; it claims just the current occurrence, never weekly or recurring responsibility. Mine → Quick Done opens your own due tasks with inline Done; unfinished checklists still open before completion. Dashboard also offers Quick Done. Today’s calendar Details opens the current card directly. The former one-button calendar preview also opens that card directly with explicit current-occurrence wording.

Who’s home adds eligible non-bot members available in the configured channel cache, preserving saved accounts/history. Each account’s usual schedule and date exceptions remain separate. Duplicate roster names include IDs. Discord may not supply every member in cache; use the existing person picker for a missing person. Full live roster verification is still required. No production schedule, preference, or chore has been edited.

This candidate requires exact GitHub push and server deployment approval under AGENTS.md. No code has been pushed or deployed. Live Discord rendering and the exact reported Everyone path still need confirmation.

Validation: all 482 offline tests passed, zero failures. Exact-source full report: ../sprig-release-tests-2.3.0.json. Generated 14 screen states fit Discord’s 40-component cap and had no detected narrow-width overflow; styling is approximate and does not prove live Discord rendering.
