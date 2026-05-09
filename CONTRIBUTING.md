# Contributing

Thanks for considering a contribution.

## Before You Start

- Read [`.docs/SPEC.md`](./.docs/SPEC.md) and [`.docs/implementation-guide.md`](./.docs/implementation-guide.md) (private to maintainers right now; published before alpha) so you know the scope.
- For non-trivial changes, open an issue first to discuss the approach.

## Development

Requirements:

- Node 20+, pnpm 9+
- Python 3.12+, uv
- Go 1.23+
- Docker + docker-compose

```bash
make dev      # bring up all containers
make test     # run unit tests across the workspace
make lint     # lint everything
```

## Code Style

- **Python:** ruff (format + lint), pyright/ty for types.
- **TypeScript:** Biome (format + lint), TypeScript strict.
- **Go:** gofmt + golangci-lint.

CI enforces these on every PR. Don't bypass.

## Commits

- Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `build:`, `ci:`).
- Keep commits small and focused — one logical change per commit.
- Don't include co-author trailers in commits.

## PRs

- Fork → branch → PR. Link the issue.
- Include tests for new behavior.
- Update relevant docs in the same PR. Don't let docs silently drift.

## License

By contributing you agree your contributions are licensed under the same terms as the file you're modifying:

- AGPL-3.0-or-later for server / app / deploy / eval-bench.
- MIT for SDK packages.

## Security

Do not open public issues for security vulnerabilities. See [SECURITY.md](./SECURITY.md).
