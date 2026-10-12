"""Central configuration for JalaJagruti AI.

Secrets are read only from the environment / .env (via python-dotenv).
Non-secret processing settings come from config/project.yaml.
Nothing here inspects credential *format*; we only check presence.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from backend.errors import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

# Credential name -> (service, where to get it)
CREDENTIALS: dict[str, tuple[str, str]] = {
    "COPERNICUS_CLIENT_ID": ("Copernicus Data Space (Sentinel-2)",
                             "https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings"),
    "COPERNICUS_CLIENT_SECRET": ("Copernicus Data Space (Sentinel-2)",
                                 "https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings"),
    "NASA_EARTHDATA_TOKEN": ("NASA Earthdata / LAADS (VIIRS VNP46A3)",
                             "https://urs.earthdata.nasa.gov/ -> Generate Token"),
    "CDS_API_KEY": ("Copernicus Climate Data Store (ERA5-Land)",
                    "https://cds.climate.copernicus.eu/profile"),
}


def _load_yaml() -> dict[str, Any]:
    path = PROJECT_ROOT / "config" / "project.yaml"
    if not path.exists():
        raise ConfigurationError(f"Missing settings file: {path}")
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class Settings:
    raw: dict[str, Any]
    root: Path = PROJECT_ROOT
    secrets: dict[str, str | None] = field(default_factory=dict)

    # ---- convenience accessors -------------------------------------------
    def section(self, name: str) -> dict[str, Any]:
        return self.raw.get(name, {}) or {}

    @property
    def groundwater_dir(self) -> Path:
        return self.root / self.section("paths").get("groundwater_dir", "GroundWaterDataset")

    @property
    def data_dir(self) -> Path:
        return self.root / self.section("paths").get("data_dir", "data")

    def dir(self, *parts: str) -> Path:
        p = self.data_dir.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cache_dir(self) -> Path: return self.dir("cache")
    @property
    def processed_dir(self) -> Path: return self.dir("processed")
    @property
    def outputs_dir(self) -> Path: return self.dir("outputs")
    @property
    def reports_dir(self) -> Path: return self.dir("reports")
    @property
    def models_dir(self) -> Path: return self.dir("models")

    @property
    def training_bbox(self) -> tuple[float, float, float, float]:
        b = self.section("region")["training_bbox"]
        return float(b[0]), float(b[1]), float(b[2]), float(b[3])

    # ---- credentials -------------------------------------------------------
    def secret(self, name: str) -> str | None:
        v = self.secrets.get(name)
        return v if v else None

    def require(self, *names: str) -> dict[str, str]:
        """Return requested credentials or raise an actionable error."""
        missing = [n for n in names if not self.secret(n)]
        if missing:
            lines = [f"  - {n}: needed for {CREDENTIALS[n][0]} (get it at {CREDENTIALS[n][1]})"
                     for n in missing]
            raise ConfigurationError(
                "Missing credentials in .env:\n" + "\n".join(lines) +
                f"\nCopy .env.example to .env in {self.root} and fill in these values.")
        return {n: self.secret(n) for n in names}  # type: ignore[misc]

    def credential_status(self) -> dict[str, bool]:
        return {n: bool(self.secret(n)) for n in CREDENTIALS}


_SETTINGS: Settings | None = None


def get_settings(reload: bool = False) -> Settings:
    global _SETTINGS
    if _SETTINGS is None or reload:
        if reload:
            load_dotenv(PROJECT_ROOT / ".env", override=True)
        secrets = {k: (os.getenv(k) or "").strip() or None for k in CREDENTIALS}
        _SETTINGS = Settings(raw=_load_yaml(), secrets=secrets)
    return _SETTINGS


def validate_project_structure(settings: Settings) -> list[str]:
    """Return a list of problems (empty list == OK)."""
    problems = []
    for rel in ["backend", "config/project.yaml", "frontend"]:
        if not (settings.root / rel).exists():
            problems.append(f"Missing project path: {rel}")
    if not (settings.root / ".env").exists():
        problems.append("No .env file found (copy .env.example to .env and add your credentials).")
    return problems
