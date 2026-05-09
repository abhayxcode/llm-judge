# Project Rules

## Git

1. **Never force-commit anything inside `.docs/`.** That directory is globally gitignored on purpose. Do not `git add -f`, do not edit `.gitignore` to include it, do not work around the ignore. If asked to "commit the docs" — push back and confirm.
2. **Commit cadence: small, frequent, clean.** After every significant unit of work (a finished step in a phase, a working feature, a passing milestone exit criterion) — commit. The goal is a clean linear history that makes rollback easy. Don't batch unrelated changes.
3. **No Claude co-author trailer.** Do not append `Co-Authored-By: Claude ...` lines. Commits should look like the human wrote them.
4. **Keep docs in sync.** After every commit / ship of a significant unit, update any doc that is now stale — SPEC, implementation guide, Architecture, progress trackers, todos. If no update is needed, leave it alone. Never let docs silently drift from code.

## Source of Truth

- `.docs/SPEC.md` — what to build.
- `.docs/implementation-guide.md` — order to build it.
- `.docs/Architecture.md` — end-of-phase diagrams.

When code drifts from these, fix the code or update the doc — don't let them silently disagree.
