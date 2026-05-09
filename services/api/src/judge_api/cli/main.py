"""judge-cli: operational CLI for migrations + bootstrap.

Subcommands:

    judge-cli migrate-pg              -- alembic upgrade head
    judge-cli migrate-ch              -- apply ClickHouse SQL files
    judge-cli bootstrap [--org slug] [--project slug]
                                      -- create default org/project/api_key
                                         and print the plaintext api_key once
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from pathlib import Path

import click

from judge_api.config import get_settings


@click.group()
def cli() -> None:
    """LLM Judge ops CLI."""


@cli.command("migrate-pg")
def migrate_pg() -> None:
    """Run alembic upgrade head against Postgres."""
    from alembic import command
    from alembic.config import Config

    cfg_path = _find_alembic_ini()
    cfg = Config(str(cfg_path))
    click.echo(f"alembic upgrade head ({cfg_path})")
    command.upgrade(cfg, "head")
    click.secho("postgres migrations applied", fg="green")


@cli.command("migrate-ch")
@click.option("--dry-run", is_flag=True, help="Print SQL without executing")
def migrate_ch(dry_run: bool) -> None:
    """Apply ClickHouse SQL migrations idempotently."""
    import clickhouse_connect

    settings = get_settings()
    sql_dir = _find_alembic_ini().parent / "migrations" / "clickhouse"
    files = sorted(sql_dir.glob("*.sql"))
    if not files:
        click.echo(f"no migration files in {sql_dir}")
        return

    if dry_run:
        for f in files:
            click.echo(f"--- {f.name}")
            click.echo(f.read_text())
        return

    client = clickhouse_connect.get_client(
        host=settings.ch_host,
        port=settings.ch_http_port,
        username=settings.ch_user,
        password=settings.ch_password,
        database=settings.ch_db,
    )
    for f in files:
        click.echo(f"applying {f.name} ...")
        sql = f.read_text()
        for stmt in _split_statements(sql):
            client.command(stmt)
    click.secho(f"applied {len(files)} clickhouse migration files", fg="green")


@cli.command("bootstrap")
@click.option("--org", "org_slug", default="default", show_default=True)
@click.option("--project", "project_slug", default="demo", show_default=True)
@click.option("--key-name", default="local-dev", show_default=True)
def bootstrap(org_slug: str, project_slug: str, key_name: str) -> None:
    """Create a default org + project + api key.

    Prints the plaintext API key exactly once. Re-running with the same
    slugs is idempotent for the org + project; the API key is only
    issued the first time.
    """
    asyncio.run(_bootstrap(org_slug, project_slug, key_name))


def _find_alembic_ini() -> Path:
    """Walk up to find services/api/alembic.ini."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "alembic.ini"
        if candidate.is_file():
            return candidate
    raise click.ClickException("alembic.ini not found relative to judge-cli")


def _split_statements(sql: str) -> list[str]:
    """Split a SQL file into individual statements terminated by `;`.

    Skips `--` line comments and `/* */` block comments so semicolons
    inside them don't trigger splits. Single-quoted strings are
    preserved as-is.
    """
    out: list[str] = []
    buf: list[str] = []
    in_str = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if not in_str:
            if ch == "-" and nxt == "-":
                in_line_comment = True
                buf.extend([ch, nxt])
                i += 2
                continue
            if ch == "/" and nxt == "*":
                in_block_comment = True
                buf.extend([ch, nxt])
                i += 2
                continue

        if ch == "'":
            in_str = not in_str

        if ch == ";" and not in_str:
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


async def _bootstrap(org_slug: str, project_slug: str, key_name: str) -> None:
    from sqlalchemy import select

    from judge_api.db.engine import get_session_factory
    from judge_api.db.models import ApiKey, Org, Project

    factory = get_session_factory()
    async with factory() as session:
        org = (await session.execute(select(Org).where(Org.slug == org_slug))).scalar_one_or_none()
        if org is None:
            org = Org(id=_ulid(), slug=org_slug, name=org_slug.replace("-", " ").title())
            session.add(org)
            await session.flush()
            click.secho(f"created org {org.slug} ({org.id})", fg="green")
        else:
            click.echo(f"org {org.slug} already exists ({org.id})")

        project = (
            await session.execute(
                select(Project).where(Project.org_id == org.id, Project.slug == project_slug)
            )
        ).scalar_one_or_none()
        if project is None:
            project = Project(
                id=_ulid(), org_id=org.id, slug=project_slug, name=project_slug.title(), settings={}
            )
            session.add(project)
            await session.flush()
            click.secho(f"created project {project.slug} ({project.id})", fg="green")
        else:
            click.echo(f"project {project.slug} already exists ({project.id})")

        existing = (
            await session.execute(
                select(ApiKey).where(ApiKey.project_id == project.id, ApiKey.name == key_name)
            )
        ).scalar_one_or_none()
        if existing is not None:
            click.secho(
                f"api_key '{key_name}' already exists; refusing to re-issue plaintext.", fg="yellow"
            )
            click.echo(f"  prefix={existing.key_prefix} created_at={existing.created_at}")
            await session.commit()
            return

        plaintext = "judge_" + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        api_key = ApiKey(
            id=_ulid(),
            project_id=project.id,
            name=key_name,
            key_hash=key_hash,
            key_prefix=plaintext[:8],
        )
        session.add(api_key)
        await session.commit()

        click.echo("")
        click.secho("API KEY (shown once):", bold=True, fg="cyan")
        click.echo(plaintext)
        click.echo("")
        click.echo("export it as JUDGE_API_KEY for the SDK to authenticate.")
        click.echo(f"project_id = {project.id}")


def _ulid() -> str:
    """Local ULID without pulling another dep."""
    import os
    import time

    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    out: list[str] = []
    for _ in range(26):
        out.append(alphabet[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


if __name__ == "__main__":
    cli()
