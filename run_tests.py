"""Offline test runner. Never imports the production bot against its live DB."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
RUNTIME = ('sprig_bot.py', 'chore_board.py', 'chore_timing.py',
           'household_availability.py', 'chore_history.py', 'chore_workspace.py',
           'chore_planning.py', 'chore_recovery.py', 'chore_insights.py', 'repeating_signups.py')
SOURCES = RUNTIME + ('requirements.txt', 'test_chore_board.py', 'run_tests.py')

# Reuse regression tests, rather than maintaining a second set of assertions.
# These cover host-dependent loading, SQLite, async callbacks, and serialization.
SERVER_CHECKS = {
    'immediate Skip and bottom Undo': 'test_manual_skip_immediate_privacy_double_tap_and_bottom_undo',
    'Skip Undo restoration and rollback': 'test_skip_undo_is_atomic_keeps_patterns_and_restores_calendar',
    'button-only chore navigation': 'test_buttons_only_real_claim_name_skip_flow_and_private_actions',
    'recurring weekday home coverage': 'test_repeating_weekdays_shared_daily_ownership_home_and_release',
    'recurring AM PM completion and Skip': 'test_repeating_am_pm_complete_skip_and_undo_preserve_patterns',
    'announcement owner permission and quiet default': 'test_announcement_controls_are_owner_only_including_forged_callbacks',
    'update notice routing and deduplication': 'test_update_notice_once_per_release_concurrent_and_no_mentions',
    'schema, legacy upgrade, saved data': 'test_bootstrap_blank_and_legacy_database_use_real_migrations',
    'fixture isolation and durability settings': 'test_fixture_template_contains_schema_without_household_state',
    'pickup Details and card Claim': 'test_pickup_details_opens_card_without_claiming_and_card_claim_still_works',
    'simultaneous Claim': 'test_audit9_competing_card_claims_in_both_orders',
    'single completion award': 'test_audit9_card_and_inline_done_together_award_once',
    'transaction rollback': 'test_audit9_completion_failure_rolls_back_points_history_and_revision',
    'restart persistence': 'test_audit9_restart_keeps_unchanged_pending_trade_valid',
    'completion Undo and rollback': 'test_workspace_completion_undo_survives_reopen_and_failed_undo_is_atomic',
    'owner-only points reset': 'test_points_reset_owner_only_button_and_forged_confirmation',
    'AM/PM ownership and completion': 'test_daily_am_pm_have_independent_weekly_owners_and_completions',
    'DST and repeat schedules': 'test_weekday_and_twice_daily_resets_across_dst',
    'Sunday handoff and attendance': 'test_exception_sunday_handoff_dst_and_separate_people',
    'adjustable defaults and dated overrides': 'test_usual_defaults_weekdays_opposite_rotation_dst_and_date_override_priority',
    'reminder opt-in and access': 'test_planning_reminders_default_off_and_personal_permissions',
    'reminder deduplication and restart': 'test_planning_reminders_deduplicate_concurrent_and_restart',
    'reminder ownership changes': 'test_audit10_reassignment_during_lookup_follows_recipient_optin',
    'reminder expiry': 'test_audit10_slot_expiring_during_lookup_is_not_sent_late',
    'moved Skip persistence': 'test_audit10_moved_monthly_skip_waits_until_next_month_and_survives_reload',
    'today-first Calendar': 'test_calendar_navigation_dashboard_defaults_to_today_at_click_time',
    'private Discord serialization': 'test_v2_serialized_private_message_has_v2_and_ephemeral_flags',
    'Discord component limits': 'test_workspace_all_screens_and_large_data_respect_discord_limits',
    'five-item pages and visible navigation': 'test_list_length_default_five_pages_keep_visible_navigation',
    'personal display preference durability': 'test_list_length_save_is_personal_validated_and_durable',
    'read-only workload arithmetic': 'test_insights_fixed_flexible_twice_daily_and_unclaimed_budget_math',
    'recovery access boundaries': 'test_recovery_rejects_wrong_person_guild_and_lost_channel_access',
    'real Discord view dispatch': 'test_recovery_real_view_store_dispatch_handles_dynamic_and_static_once',
}


def source_hashes():
    # Git may check out CRLF on Windows and LF on Linux; compare source content.
    return {name: hashlib.sha256((HERE / name).read_text(encoding='utf-8').encode('utf-8')).hexdigest() for name in SOURCES}


def validate_release(report, hashes, names):
    """Fail closed: small server checks supplement a full pass of these sources."""
    if (not isinstance(report, dict) or report.get('suite') != 'full' or report.get('success') is not True
            or report.get('tests_run') != len(names) or report.get('test_names') != names
            or report.get('skipped') != 0 or report.get('source_hashes') != hashes):
        raise ValueError('Release report is not a complete passing run of these exact sources. Run the full suite again.')


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timings = []

    def startTest(self, test):
        self.started = perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        self.timings.append({'test': test._testMethodName,
                             'seconds': round(perf_counter() - self.started, 6),
                             'setup_seconds': round(getattr(test, 'setup_seconds', 0), 6)})
        super().stopTest(test)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('full', 'server', 'focused'), default='full')
    parser.add_argument('--match', action='append', default=[], help='Focused test name substring; repeat to combine.')
    parser.add_argument('--release-report', type=Path, help='Passing full-run JSON required for smaller server checks.')
    parser.add_argument('--report', type=Path, help='Write results and source fingerprints to this JSON file.')
    parser.add_argument('--cold-start', action='store_true', help='Rebuild the schema for every test (comparison/diagnosis).')
    parser.add_argument('--profile', action='store_true', help='Show setup time and the ten slowest tests.')
    parser.add_argument('--list', action='store_true', help='List selected tests without running them.')
    args = parser.parse_args(argv)
    if args.match and args.suite != 'focused':
        parser.error('--match requires --suite focused')
    if args.suite == 'focused' and not args.match:
        parser.error('focused requires at least one --match')
    if args.report and args.release_report and args.report.resolve() == args.release_report.resolve():
        parser.error('server results must not overwrite the full release report')

    # Imports discord.py and the test harness, not a live bot. Each test imports
    # the bot from its own temporary folder with a dummy token and mocked DMs.
    from test_chore_board import BoardTests
    names = unittest.defaultTestLoader.getTestCaseNames(BoardTests)
    if len(set(SERVER_CHECKS.values())) != len(SERVER_CHECKS):
        parser.error('server manifest repeats a test')
    missing = set(SERVER_CHECKS.values()) - set(names)
    if missing:
        parser.error('server checks missing from suite: ' + ', '.join(sorted(missing)))
    if args.suite == 'server':
        selected = list(SERVER_CHECKS.values())
    elif args.suite == 'focused':
        selected = [n for n in names if any(m in n for m in args.match)]
    else:
        selected = names
    if not selected:
        parser.error('no matching tests; nothing was verified')
    if args.list:
        print('\n'.join(selected))
        print(f'{len(selected)} tests')
        return 0
    hashes = source_hashes()
    if args.suite == 'server':
        if not args.release_report:
            parser.error('server checks require --release-report from the full local pass')
        try:
            validate_release(json.loads(args.release_report.read_text(encoding='utf-8')), hashes, names)
        except (OSError, ValueError, TypeError) as error:
            parser.error(str(error))
    # This also catches a missing or syntactically broken runtime module on host.
    for name in RUNTIME:
        compile((HERE / name).read_bytes(), name, 'exec')
    started = perf_counter()
    with patch.dict(os.environ, SPRIG_TEST_COLD_START='1' if args.cold_start else '0'):
        result = unittest.TextTestRunner(verbosity=1, resultclass=TimedResult).run(
            unittest.TestSuite(BoardTests(name) for name in selected))
    unchanged = source_hashes() == hashes
    success = result.wasSuccessful() and not result.skipped and result.testsRun == len(selected) and unchanged
    report = {'suite': args.suite, 'success': success, 'tests_run': result.testsRun,
              'test_names': selected, 'skipped': len(result.skipped), 'source_hashes': hashes,
              'seconds': round(perf_counter() - started, 6), 'cold_start': args.cold_start,
              'timings': result.timings, 'sources_unchanged': unchanged}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if args.profile:
        print(f"Setup total: {sum(t['setup_seconds'] for t in result.timings):.3f}s")
        for row in sorted(result.timings, key=lambda t: t['seconds'], reverse=True)[:10]:
            print(f"{row['seconds']:.3f}s (setup {row['setup_seconds']:.3f}s) {row['test']}")
    if not unchanged:
        print('Sources changed during this run; report cannot approve a release.', file=sys.stderr)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
