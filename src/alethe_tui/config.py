"""Configuração local: descoberta explícita, sem alterar os executores."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Config:
    roots: list[Path]
    claude_root: Path
    codex_root: Path
    interval: float = 1.0
    verify_pids: bool = True


def load_config(path: Path | None = None, environ: Mapping[str, str] | None = None,
                roots: list[Path] | None = None, claude_root: Path | None = None,
                codex_root: Path | None = None) -> Config:
    env = os.environ if environ is None else environ
    home = Path(env.get("HOME", str(Path.home())))
    base = Path(env.get("XDG_CONFIG_HOME", str(home / ".config")))
    path = path or base / "alethe-tui/config.toml"
    try:
        with path.open("rb") as handle:
            settings = tomllib.load(handle)
    except FileNotFoundError:
        settings = {}
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"Configuração inválida em {path}: {error}") from error

    def expand(value):
        raw = str(value)
        if raw == "~" or raw.startswith("~/"):
            raw = str(home) + raw[1:]
        return Path(raw).resolve()

    configured = settings.get("roots", [])
    if not isinstance(configured, list) or not all(isinstance(x, str) for x in configured):
        raise ValueError("roots deve ser uma lista de caminhos")
    policy = expand(env.get("ALETHE_ORCHESTRATE_POLICY", str(base / "alethe/orchestrate.json")))
    candidates = [policy.parent / "orchestrations"]
    if env.get("ALETHE_ORCHESTRATE_HOME"):
        candidates.append(expand(env["ALETHE_ORCHESTRATE_HOME"]))
    candidates.extend(expand(p) for p in configured)
    candidates.extend(expand(p) for p in roots or [])
    interval = settings.get("interval", 1.0)
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval < 0.1:
        raise ValueError("interval deve ser um número maior ou igual a 0.1 segundo")
    verify = settings.get("verify_pids", True)
    if not isinstance(verify, bool):
        raise ValueError("verify_pids deve ser true ou false")
    return Config(
        list(dict.fromkeys(expand(p) for p in candidates)),
        expand(claude_root or settings.get("claude_root") or Path(env.get("CLAUDE_CONFIG_DIR", str(home / ".claude"))) / "projects"),
        expand(codex_root or settings.get("codex_root") or Path(env.get("CODEX_HOME", str(home / ".codex"))) / "sessions"),
        float(interval), verify,
    )
