"""Invarians SDK — Response models and chain metadata."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal

# ──────────────────────────────────────────────────────────────
# Types
# ──────────────────────────────────────────────────────────────

Regime = Literal["S1D1", "S1D2", "S2D1", "S2D2"]
BridgeState = Literal["BS1", "BS2"]                 # native bridges
CcipState   = Literal["CS1", "CS2"]                 # CCIP lanes (calibrated ≥ P3)
CctpState   = Literal["TS1", "TS2"]                 # CCTP routes (calibrated ≥ P3)
AnyBridgeState = Literal["BS1", "BS2", "CS1", "CS2", "TS1", "TS2"]
CircleApiStatus = Literal["OK", "DEGRADED", "UNAVAILABLE"]
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
    # L2 — LOW until 25 Apr 2026 (τ structurally dormant on all rollups, π baselines converging)
    "arbitrum":  ChainMeta("arbitrum",  m1_validated=False, tau_calibrated=False, pi_calibrated=True,  calibration_confidence="LOW",
                           notes="τ dormant (max 1.029, threshold 1.15) — S2D1/S2D2 unreachable. σ excluded (rho_s=0 bug). Full calibration 25 Apr 2026."),
    "base":      ChainMeta("base",      m1_validated=False, tau_calibrated=True,  pi_calibrated=True,  calibration_confidence="LOW",
                           notes="τ=1.0000 fixed (OP Stack 2s sequencer) — S2D1/S2D2 unreachable. π baselines converging until ~2026-04-16. Full calibration 25 Apr 2026."),
    "optimism":  ChainMeta("optimism",  m1_validated=False, tau_calibrated=True,  pi_calibrated=True,  calibration_confidence="LOW",
                           notes="τ=1.0000 fixed (OP Stack 2s sequencer) — S2D1/S2D2 unreachable. π baselines converging until ~2026-04-16. Full calibration 25 Apr 2026."),
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
    index_a: float                   # σ computational load (sigma_ratio)
    index_b: float                   # data load (size_ratio)
    index_c: float                   # operational load (tx_ratio)
    # L2 extended signals (Phase A/B/C — null until calibrated ~2026-04-25)
    index_d: Optional[float] = None  # complexity_ratio (Phase A)
    index_e: Optional[float] = None  # gas_complexity_ratio (Phase B)
    index_f: Optional[float] = None  # publish_latency_seconds (Phase C)
    index_g: Optional[float] = None  # blob_usage (Phase C)
    index_h: Optional[float] = None  # calldata_per_tx (Phase C)


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
    tau_computed_at: Optional[str] = None  # timestamp of structural signal (standalone only)
    pi_computed_at: Optional[str] = None   # timestamp of demand signal (standalone only)
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
    """Response from GET /attestation/execution-context

    DEPRECATED (2026-04-20): the execution-context endpoint returns 410 Gone.
    Use `InvariansClient.get_panel()` and `PanelResponse` instead. The AI agent
    composes routes client-side from the panel (no `from/to` in the API).
    """
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


# ──────────────────────────────────────────────────────────────
# PANEL API (v1.0 — 2026-04-20 — pivot panel-based)
# ──────────────────────────────────────────────────────────────
#
# GET /attestation/panel returns a panel of independent L1/L2/bridge states.
# The AI agent composes its routes client-side. No direction in the API.
#
# Bridge IDs are canonical: "{chainA}-{chainB}/{type}", sorted alphabetically
# by the backend where applicable. `endpoints` lists both endpoints (order
# not semantically meaningful: bridge state is direction-agnostic).

ItemStatus = Literal["OK", "STALE", "UNAVAILABLE", "UNCALIBRATED"]
OracleStatusV1 = Literal["OK", "DEGRADED"]
BridgeType = Literal["native", "ccip", "cctp"]


@dataclass
class L1Entry:
    """L1 chain state inside the panel."""
    chain: str
    regime: Optional[Regime]
    status: ItemStatus
    computed_at: Optional[str]
    window: str                           # "1h"
    divergence_index: Optional[float]
    structural: StructuralSignals
    execution_profile: ExecutionProfile
    meta: Optional[ChainMeta] = None      # enriched by SDK


@dataclass
class L2Entry:
    """L2 chain state inside the panel."""
    chain: str
    regime: Optional[Regime]
    status: ItemStatus
    computed_at: Optional[str]
    window: str                           # "1h"
    structural: StructuralSignals
    execution_profile: ExecutionProfile
    meta: Optional[ChainMeta] = None


@dataclass
class BridgeEntry:
    """Bridge state inside the panel.

    Type-specific semantics :
      - native (direction-agnostic, e.g. "arbitrum-ethereum/native") :
          raw signal = `last_batch_age_seconds` ; state ∈ {BS1, BS2}
      - ccip   (directional,       e.g. "ethereum-arbitrum/ccip") :
          raw signal = `last_sequence_advance_seconds` + RMN binary override ;
          state ∈ {CS1, CS2} (calibrated ≥ P3)
      - cctp   (directional,       e.g. "ethereum-arbitrum/cctp") :
          raw signal = `attestation_latency_p90_s` + Circle Iris API status ;
          state ∈ {TS1, TS2} (calibrated ≥ P3)

    In P2 (J5 2026-04-24), CCIP/CCTP entries are exposed with raw fields but
    `status="UNCALIBRATED"` and `state=None` until P3 seeds fill `threshold_bs1_s`
    in `bridge_thresholds` (requires ≥30j of samples for P97).
    """
    id: str
    endpoints: list[str]
    type: BridgeType
    state: Optional[AnyBridgeState]       # None while calibrated=False or STALE/UNAVAILABLE
    calibrated: bool
    status: ItemStatus
    observed_at: Optional[str]
    window: str                           # "10m" native, "1h" ccip/cctp
    last_batch_age_seconds: Optional[float] = None  # native raw (exposed when uncalibrated)

    # CCIP raw signals (populated when type=="ccip", None otherwise)
    last_sequence_advance_seconds: Optional[float] = None
    sequence_gap:                  Optional[int]   = None
    commit_latency_p90_s:          Optional[float] = None
    execute_latency_p90_s:         Optional[float] = None
    total_latency_p90_s:           Optional[float] = None
    rmn_cursed:                    Optional[bool]  = None  # RMN binary override (P2+)

    # CCTP raw signals (populated when type=="cctp", None otherwise)
    attestation_latency_p90_s:     Optional[float] = None
    attestation_latency_p99_s:     Optional[float] = None
    attestation_success_rate_1h:   Optional[float] = None
    circle_api_status:             Optional[CircleApiStatus] = None

    @property
    def is_frozen(self) -> bool:
        """True if CCIP RMN is cursed (lane frozen) — absolute binary override."""
        return self.type == "ccip" and self.rmn_cursed is True

    @property
    def is_circle_api_healthy(self) -> bool:
        """True if this is a CCTP entry and Circle Iris API is reporting OK."""
        return self.type == "cctp" and self.circle_api_status == "OK"


@dataclass
class Coverage:
    l1_chains: list[str]
    l2_chains: list[str]
    bridges_native: int
    bridges_ccip: int
    bridges_cctp: int
    methodology_url: str


@dataclass
class SignedExecutionContext:
    """Signed attestation of the panel payload.

    `anchor` is None in V1 (HMAC only). Populated in V1.1+ with on-chain
    anchor {tx_hash, block_number, contract} after InvariansAnchor deploy
    on Arbitrum (targeted May 2026).
    """
    payload_hash: str                     # "0x{sha256(canonical_json(panel))}"
    signature: str                        # "hmac-sha256:{hex}"
    key_id: str                           # "invarians-v1"
    anchor: Optional[dict] = None         # {tx_hash, block_number, contract} when anchored


@dataclass
class PanelResponse:
    """Full response from GET /attestation/panel."""
    version: str                          # "1.0.0"
    oracle_status: OracleStatusV1         # "OK" | "DEGRADED"
    issued_at: str
    l1: list[L1Entry]
    l2: list[L2Entry]
    bridges: list[BridgeEntry]
    coverage: Coverage
    signed_execution_context: SignedExecutionContext

    def bridge_by_id(self, bridge_id: str) -> Optional[BridgeEntry]:
        for b in self.bridges:
            if b.id == bridge_id:
                return b
        return None

    def l1_by_chain(self, chain: str) -> Optional[L1Entry]:
        for e in self.l1:
            if e.chain == chain:
                return e
        return None

    def l2_by_chain(self, chain: str) -> Optional[L2Entry]:
        for e in self.l2:
            if e.chain == chain:
                return e
        return None

    @property
    def is_fully_ok(self) -> bool:
        """True if all items report OK (not STALE/UNAVAILABLE/UNCALIBRATED)."""
        return (
            all(e.status == "OK" for e in self.l1)
            and all(e.status == "OK" for e in self.l2)
            and all(b.status == "OK" for b in self.bridges)
        )
