"""
invarians — Python SDK for the Invarians Oracle API

Cross-chain infrastructure attestations: L1/L2 regimes and bridge states,
exposed as a direction-agnostic panel. The AI agent composes routes.

Quick start v2.0 (recommended, 2026-04-30+):
    from invarians import InvariansClient

    client = InvariansClient(api_key="inv_your_key")
    panel  = client.get_panel_v2(include="diagnostic")

    eth = panel.l1_by_chain("ethereum")
    print(eth.regime)                           # "S1D1" | "S1D2+" | ... (12 codes)
    print(eth.drift.demand)                     # composite drift magnitude
    print(eth.drift.demand_magnitude_delta)     # > 0 deviation grows, < 0 reverts
    print(eth.demand.tx.shift)                  # per-metric shift vs 30d baseline

    arb = panel.l2_by_chain("arbitrum")
    print(arb.structural.sequencer_publish_latency.seconds)  # raw L2 sequencer latency

    # Verify HMAC integrity
    ok = client.verify_panel_v2(panel_payload_dict, panel.signed_execution_context.signature)

Quick start v1.0 (deprecated 60d after v2.0 launch):
    panel = client.get_panel()
    eth   = panel.l1_by_chain("ethereum")
    print(eth.regime, eth.status)
"""

from .client import InvariansClient
from .models import (
    # Legacy (kept for import compatibility; methods raise NotImplementedError)
    L1Attestation,
    L2Attestation,
    ExecutionContextAttestation,
    ProofOfExecutionContext,
    # Shared
    ChainMeta,
    chain_meta,
    stale_action,
    STALE_THRESHOLD_S,
    STALE_WAIT_S,
    StructuralSignals,
    StructuralSlow,
    Shifts,
    ExecutionProfile,
    # Panel API v1.0 (2026-04-20)
    PanelResponse,
    L1Entry,
    L2Entry,
    BridgeEntry,
    Coverage,
    SignedExecutionContext,
    # Panel API v2.0 (2026-04-30 — three primitives)
    V2PanelResponse,
    V2L1Entry,
    V2L2Entry,
    V2L1Structural,
    V2L1Demand,
    V2L2Structural,
    V2L2Demand,
    V2Drift,
    V2Coverage,
    MetricBlock,
    IncludeMode,
)
from .exceptions import (
    InvariansError,
    AuthError,
    NotFoundError,
    RateLimitError,
    StaleError,
    ServerError,
)

__version__ = "0.6.1"
__all__ = [
    "InvariansClient",
    # Panel API v2.0
    "V2PanelResponse",
    "V2L1Entry",
    "V2L2Entry",
    "V2L1Structural",
    "V2L1Demand",
    "V2L2Structural",
    "V2L2Demand",
    "V2Drift",
    "V2Coverage",
    "MetricBlock",
    "IncludeMode",
    # Panel API v1.0
    "PanelResponse",
    "L1Entry",
    "L2Entry",
    "BridgeEntry",
    "Coverage",
    "SignedExecutionContext",
    # Shared
    "StructuralSignals",
    "StructuralSlow",
    "Shifts",
    "ExecutionProfile",
    "ChainMeta",
    "chain_meta",
    "stale_action",
    "STALE_THRESHOLD_S",
    "STALE_WAIT_S",
    # Legacy (deprecated)
    "L1Attestation",
    "L2Attestation",
    "ExecutionContextAttestation",
    "ProofOfExecutionContext",
    # Exceptions
    "InvariansError",
    "AuthError",
    "NotFoundError",
    "RateLimitError",
    "StaleError",
    "ServerError",
]
