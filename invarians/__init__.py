"""
invarians — Python SDK for the Invarians Oracle API

Cross-chain infrastructure attestations: L1/L2 regimes and bridge states,
exposed as a direction-agnostic panel. The AI agent composes routes.

Quick start (v0.2+):
    from invarians import InvariansClient

    client = InvariansClient(api_key="inv_your_key")
    panel  = client.get_panel()

    eth    = panel.l1_by_chain("ethereum")
    arb    = panel.l2_by_chain("arbitrum")
    bridge = panel.bridge_by_id("arbitrum-ethereum/native")

    print(panel.oracle_status)                  # "OK" | "DEGRADED"
    print(eth.regime, eth.status)               # "S1D1" "OK"
    print(bridge.state, bridge.calibrated)      # "BS1" True  (or None, False pre-P1)

    # Verify HMAC signature of the panel
    ok = client.verify_panel(panel_payload_dict, panel.signed_execution_context.signature)
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
)
from .exceptions import (
    InvariansError,
    AuthError,
    NotFoundError,
    RateLimitError,
    StaleError,
    ServerError,
)

__version__ = "0.3.0"
__all__ = [
    "InvariansClient",
    # Panel API
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
