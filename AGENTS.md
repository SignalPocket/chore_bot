# Sprig release instructions

- Every new release must increment APP_VERSION in chore_board.py before testing or deployment. Use MAJOR.MINOR.PATCH: patch for fixes, minor for backward-compatible features, major for breaking changes.
- Update CHANGELOG.md and the version-dependent announcement test with the same version. Restarts and retries of the same release keep its version.
- Follow BUTTON-BOARD.md and TESTING.md. Run the full offline suite and preserve the exact-source release report.
- Preparing a version is not deployment. Obtain Katherine's explicit approval for the exact GitHub push and server deployment. Preserve the live database, credentials, and announcement opt-in settings.
