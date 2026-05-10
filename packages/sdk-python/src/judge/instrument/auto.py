"""Auto-installer dispatch — calls into per-library patchers."""

from __future__ import annotations

from collections.abc import Callable

from judge.instrument._anthropic import install as install_anthropic
from judge.instrument._anthropic import uninstall as uninstall_anthropic
from judge.instrument._openai import install as install_openai
from judge.instrument._openai import uninstall as uninstall_openai

_INSTALLED: list[Callable[[], None]] = []


def install() -> list[str]:
    """Patch every supported library that's importable. Returns the list
    of library names actually patched."""
    if _INSTALLED:
        return []  # already installed
    patched: list[str] = []
    for name, patcher, unpatcher in (
        ("openai", install_openai, uninstall_openai),
        ("anthropic", install_anthropic, uninstall_anthropic),
    ):
        if patcher():
            patched.append(name)
            _INSTALLED.append(unpatcher)
    return patched


def uninstall() -> None:
    """Restore originals for every library `install()` patched."""
    while _INSTALLED:
        _INSTALLED.pop()()
