"""Runtime configuration.

Everything Arborist needs is read from the environment once, at import of
:func:`load_settings`, so that the rest of the code never touches ``os.environ``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

# Nemotron tiers on Nebius Token Factory. The whole point of the three-tier
# split is cost: Nano does the wide, throwaway work (one call per candidate
# patch), Super does the single reasoning-heavy diagnosis per node, and Ultra is
# only woken up when the search is genuinely stuck or two branches tie.
# Exactly as Token Factory serves them -- `GET /v1/models` is the source of
# truth and the ids are case-sensitive. The lowercase slugs used by model
# aggregators 404 here.
MODEL_NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
MODEL_SUPER = "nvidia/nemotron-3-super-120b-a12b"
MODEL_ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"

TIERS = {"nano": MODEL_NANO, "super": MODEL_SUPER, "ultra": MODEL_ULTRA}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    # --- credentials ---------------------------------------------------------
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    contree_base_url: str = "https://api.tokenfactory.nebius.com/sandboxes"
    nebius_project_id: str = ""
    tavily_api_key: str = ""

    # --- search shape --------------------------------------------------------
    backend: str = "contree"
    branching: bool = True
    fanout: int = 4
    max_nodes: int = 24
    max_depth: int = 4
    token_budget: int = 1_500_000

    # --- sandbox -------------------------------------------------------------
    default_image: str = "python:3.12-slim"
    exec_timeout: float = 900.0

    # --- serving -------------------------------------------------------------
    runs_dir: str = "runs"
    demo_run: str = ""
    """A saved run report to show when the page opens.

    A deployed demo should display a real, finished search to someone who has
    not configured anything -- empty state teaches nobody. Defaults to the most
    recent report in ``runs_dir``.
    """

    models: dict[str, str] = field(default_factory=lambda: dict(TIERS))

    @property
    def has_llm(self) -> bool:
        return bool(self.nebius_api_key)

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key)


def load_settings(**overrides) -> Settings:
    """Build settings from the environment, with explicit overrides on top."""
    base = Settings(
        nebius_api_key=os.environ.get("NEBIUS_API_KEY", ""),
        nebius_base_url=os.environ.get("NEBIUS_BASE_URL") or Settings.nebius_base_url,
        contree_base_url=os.environ.get("CONTREE_BASE_URL") or Settings.contree_base_url,
        nebius_project_id=os.environ.get("NEBIUS_PROJECT_ID", ""),
        tavily_api_key=os.environ.get("TAVILY_API_KEY", ""),
        backend=os.environ.get("ARBORIST_BACKEND") or Settings.backend,
        branching=_flag("ARBORIST_BRANCHING", True),
        fanout=_int("ARBORIST_FANOUT", Settings.fanout),
        max_nodes=_int("ARBORIST_MAX_NODES", Settings.max_nodes),
        max_depth=_int("ARBORIST_MAX_DEPTH", Settings.max_depth),
        token_budget=_int("ARBORIST_TOKEN_BUDGET", Settings.token_budget),
        runs_dir=os.environ.get("ARBORIST_RUNS_DIR") or Settings.runs_dir,
        demo_run=os.environ.get("ARBORIST_DEMO_RUN", ""),
    )
    if overrides:
        clean = {k: v for k, v in overrides.items() if v is not None}
        return Settings(**{**base.__dict__, **clean})
    return base
