"""Central configuration (pydantic-settings). Every knob in PRD §21 lives here."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # ---- LLM (PRD §15: model version is pinned and recorded with every output) ----
    gemini_api_key: str = ""
    llm_model: str = "gemini-2.5-pro"
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 4000
    llm_send_raw_code: bool = False
    llm_timeout_seconds: float = 90.0

    # ---- Datastores ----
    # Neo4j is OPTIONAL. The knowledge graph always lives in the embedded store
    # (NetworkX + SQLite); setting neo4j_uri additionally mirrors it to Neo4j.
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    database_url: str = ""
    data_dir: Path = REPO_ROOT / "data"

    # ---- Engine 4: decomposition ----
    decomp_weights: str = "0.30,0.20,0.25,0.10,0.15"
    decomp_gamma: float = 1.5
    decomp_alpha: float = 1.0
    decomp_beta: float = 1.0
    hdbscan_min_cluster_size: int = 4

    # ---- Engine 6: roadmap ----
    montecarlo_runs: int = 10000
    montecarlo_seed: int = 20260413
    roadmap_solver_seconds: float = 10.0
    squad_count: int = 3

    # ---- Engine 5: effort model ----
    gxp_multiplier_high: float = 1.8
    gxp_multiplier_medium: float = 1.3
    gxp_multiplier_low: float = 1.0

    @property
    def weights(self) -> list[float]:
        parts = [float(x) for x in self.decomp_weights.split(",") if x.strip()]
        if len(parts) != 5:
            raise ValueError("DECOMP_WEIGHTS must list 5 floats (structural,runtime,data,cochange,semantic)")
        total = sum(parts)
        return [p / total for p in parts] if total else parts

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def packs_dir(self) -> Path:
        return self.data_dir / "packs"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            if self.database_url.startswith("sqlite:///") and not (
                self.database_url.startswith("sqlite:////") or (len(self.database_url) > 11 and self.database_url[11] == ":")
            ):
                rel = self.database_url[10:]
                return f"sqlite:///{(REPO_ROOT / rel).as_posix()}"
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'modernrx.db').as_posix()}"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.gemini_api_key.strip())

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.packs_dir):
            d.mkdir(parents=True, exist_ok=True)

    def gxp_multiplier(self, tier: str) -> float:
        return {
            "HIGH": self.gxp_multiplier_high,
            "MEDIUM": self.gxp_multiplier_medium,
        }.get((tier or "LOW").upper(), self.gxp_multiplier_low)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
