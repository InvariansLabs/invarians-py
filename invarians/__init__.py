"""
invarians — Python SDK for the Invarians Oracle API

Cross-layer blockchain infrastructure attestations:
structural health (τ), demand pressure (π), and bridge liveness.

Quick start:
    from invarians import InvariansClient

    client = InvariansClient(api_key="inv_your_key")
    ctx = client.get_execution_context(l1="ethereum", l2="arbitrum")

    print(ctx.proof.pattern_key)          # "S1D1×S1D1×BS1"
    print(ctx.proof.l1_regime)            # "S1D1"
    print(ctx.stale_action)               # "ok" | "caution" | "wait"
    print(ctx.l1.meta.is_actionable())    # True (ETH is calibrated)
"""

from .client import InvariansClient
from .models import (
    L1Attestation,
    L2Attestation,
    ExecutionContextAttestation,
    ProofOfExecutionContext,
    ChainMeta,
    chain_meta,
    stale_action,
    STALE_THRESHOLD_S,
    STALE_WAIT_S,
)
from .exceptions import (
    InvariansError,
    AuthError,
    NotFoundError,
    RateLimitError,
    StaleError,
    ServerError,
)

__version__ = "0.1.0"
__all__ = [
    "InvariansClient",
    "L1Attestation",
    "L2Attestation",
    "ExecutionContextAttestation",
    "ProofOfExecutionContext",
    "ChainMeta",
    "chain_meta",
    "stale_action",
    "STALE_THRESHOLD_S",
    "STALE_WAIT_S",
    "InvariansError",
    "AuthError",
    "NotFoundError",
    "RateLimitError",
    "StaleError",
    "ServerError",
]
