"""Invarians SDK — Response models and chain metadata."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal

# ──────────────────────────────────────────────────────────────
# Types
# ──────────────────────────────────────────────────────────────

Regime = Literal["S1D1", "S1D2", "S2D1", "S2D2"]
BridgeState = Literal["BS1", "BS2"]
OracleStatus = Literal["OK", "STALE"]
StaleAction = Literal["ok", "caution", "wait"]

# ──────────────────────────────────────────────────────────────
# Chain confidence metadata (static, based on calibration status)
# ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ChainMeta:
    """Static quality metadata for a chain's signal."""
    chain: str
    m1_validated: bool          # True = backtest validated (ETH, POL)
    tau_calibrated: bool        # τ (structural) signal calibrated
    pi_calibrated: bool         # π (demand) signal calibrated
    calibration_confidence: Literal["HIGH", "MEDIUM", "LOW", "NONE"]
    notes: str = ""

    def is_actionable(self) -> bool:
        """Returns True if signal is reliable enough for agent decisions."""
        return self.m1_validated and self.calibration_confidence in ("HIGH", "MEDIUM")


# Known chain metadata — updated as calibration progresses
_CHAIN_META: dict[str, ChainMeta] = {
    # L1
    "ethereum":  ChainMeta("ethereum",  m1_validated=True,  tau_calibrated=True,  pi_calibrated=True,  calibration_confidence="MEDIUM"),
    "polygon":   ChainMeta("polygon",   m1_validated=True,  tau_calibrated=True,  pi_calibrated=True,  calibration_confidence="MEDIUM"),
    "solana":    ChainMeta("solana",    m1_validated=False, tau_calibrated=True,  pi_calibrated=False, calibration_confidence="LOW",
                           notes="π not calibrated (no tx_count in BigQuery). τ only."),
    "avalanche": ChainMeta("avalanche", m1_validated=False, tau_calibrated=False, pi_calibrated=False, calibration_confidence="NONE",
                           notes="No BigQuery dataset. Both axes uncalibrated. Indicative only."),
    # L2 — 7-day calibration (2026-03-22), baselines converging until ~2026-04-16
    "arbitrum":  ChainMeta("arbitrum",  m1_validated=False, tau_calibrated=False, pi_calibrated=True,  calibration_confidence="MEDIUM",
                           notes="τ dormant (max 1.029, threshold 1.15). σ excluded (rho_s=0 bug). D2 uses size+tx 2-of-2."),
    "base":      ChainMeta("base",      m1_validated=False, tau_calibrated=True,  pi_calibrated=True,  calibration_confidence="MEDIUM",
                           notes="τ=1.0000 in nominal conditions (OP Stack 2s fixed block time, FPR≈0%). π baselines converging until ~2026-04-16."),
    "optimism":  ChainMeta("optimism",  m1_validated=False, tau_calibrated=True,  pi_calibrated=True,  calibration_confidence="MEDIUM",
                           notes="τ=1.0000 in nominal conditions (OP Stack 2s fixed block time, FPR≈0%). π baselines converging until ~2026-04-16."),
}


def chain_meta(chain: str) -> ChainMeta:
    """Return static calibration metadata for a chain."""
    return _CHAIN_META.get(chain.lower(), ChainMeta(
        chain, m1_validated=False, tau_calibrated=False,
        pi_calibrated=False, calibration_confidence="NONE",
        notes="Unknown chain.",
    ))


# ──────────────────────────────────────────────────────────────
# STALE policy
# ──────────────────────────────────────────────────────────────

# Thresholds from developers.html section 10
STALE_THRESHOLD_S = 3600       # above this → oracle_status = "STALE"
STALE_CAUTION_S   = 3600       # STALE and age < STALE_WAIT_S → caution
STALE_WAIT_S      = 7200       # STALE and age >= this → WAIT


def stale_action(oracle_status: str, data_age_seconds: Optional[float]) -> StaleAction:
    """
    Returns the recommended stale action based on oracle status and data age.

    ok      — data is fresh, proceed normally
    caution — data is STALE but < 2h old; use last known value with caution
    wait    — data is STALE and >= 2h old; hold decisions
    """
    if oracle_status != "STALE":
        return "ok"
    age = data_age_seconds or 0
    return "wait" if age >= STALE_WAIT_S else "caution"


# ──────────────────────────────────────────────────────────────
# Response models
# ──────────────────────────────────────────────────────────────

@dataclass
class StructuralSignals:
    rhythm_ratio: float
    continuity_ratio: float


@dataclass
class ExecutionProfile:
    """σ/π signal indices. index_a=sigma_ratio, index_b=size_ratio, index_c=tx_ratio."""
    index_a: float   # σ computational load (sigma_ratio)
    index_b: float   # data load (size_ratio)
    index_c: float   # operational load (tx_ratio)


@dataclass
class BeaconData:
    """ETH-only beacon chain participation."""
    participation: Optional[float]
    epoch: Optional[int]
    age_seconds: Optional[float]


@dataclass
class L1Attestation:
    """Response from GET /attestation/{chain}"""
    chain: str
    oracle_status: OracleStatus
    regime: Regime
    structural: StructuralSignals
    execution_profile: ExecutionProfile
    divergence_index: float
    data_age_seconds: float
    issued_at: str
    expires_at: str
    signature: str
    version: str = "v2"
    l2_verified: bool = False
    beacon: Optional[BeaconData] = None
    # Enriched by SDK (not in raw API)
    meta: Optional[ChainMeta] = None

    @property
    def stale_action(self) -> StaleAction:
        return stale_action(self.oracle_status, self.data_age_seconds)

    def is_actionable(self) -> bool:
        """True if data is fresh AND chain calibration is reliable."""
        return (self.stale_action == "ok" and
                self.meta is not None and self.meta.is_actionable())


@dataclass
class L2Attestation:
    """Response from GET /attestation/l2/{chain}"""
    chain: str
    oracle_status: OracleStatus
    regime: Regime
    structural: StructuralSignals
    execution_profile: ExecutionProfile
    data_age_seconds: float
    issued_at: str
    expires_at: str
    signature: str
    version: str = "v2"
    meta: Optional[ChainMeta] = None

    @property
    def stale_action(self) -> StaleAction:
        return stale_action(self.oracle_status, self.data_age_seconds)


@dataclass
class ProofOfExecutionContext:
    l1_regime: Regime
    l2_regime: Optional[Regime]
    bridge_state: BridgeState
    bridge_calibrated: bool = False  # False until Phase 2C (~2026-04-22)

    @property
    def pattern_key(self) -> str:
        """e.g. 'S1D2×S1D1×BS1'"""
        l2 = self.l2_regime or "NULL"
        return f"{self.l1_regime}×{l2}×{self.bridge_state}"

    @property
    def bridge_is_placeholder(self) -> bool:
        """True when bridge signal is not yet calibrated (pre-Phase 2C)."""
        return not self.bridge_calibrated


@dataclass
class ExecutionContextAttestation:
    """Response from GET /attestation/execution-context"""
    oracle_status: OracleStatus
    proof: ProofOfExecutionContext
    l1: L1Attestation
    l2: Optional[L2Attestation]
    bridge_state: BridgeState
    signature: str

    @property
    def stale_action(self) -> StaleAction:
        # Use worst stale state across L1 and L2
        l1_action = stale_action(self.oracle_status, self.l1.data_age_seconds)
        if self.l2:
            l2_action = stale_action(self.oracle_status, self.l2.data_age_seconds)
            order = ["ok", "caution", "wait"]
            return order[max(order.index(l1_action), order.index(l2_action))]  # type: ignore
        return l1_action

    def is_actionable(self) -> bool:
        return self.stale_action == "ok" and self.l1.is_actionable()
