"""
Tests SDK invarians — client, models, stale policy.
Run: pytest invarians-sdk/tests/
"""

import pytest
from invarians import (
    InvariansClient, AuthError, StaleError,
    chain_meta, stale_action,
    STALE_THRESHOLD_S, STALE_WAIT_S,
)
from invarians.models import ProofOfExecutionContext


# ──────────────────────────────────────────────────────────────
# Auth validation
# ──────────────────────────────────────────────────────────────

def test_invalid_api_key_raises():
    with pytest.raises(AuthError):
        InvariansClient(api_key="bad_key")

def test_valid_key_prefix_accepted():
    client = InvariansClient(api_key="inv_test_key_12345")
    assert client is not None


# ──────────────────────────────────────────────────────────────
# Chain metadata
# ──────────────────────────────────────────────────────────────

def test_ethereum_is_actionable():
    meta = chain_meta("ethereum")
    assert meta.m1_validated is True
    assert meta.is_actionable() is True

def test_avalanche_not_actionable():
    meta = chain_meta("avalanche")
    assert meta.m1_validated is False
    assert meta.is_actionable() is False

def test_solana_tau_calibrated_but_pi_not():
    meta = chain_meta("solana")
    assert meta.tau_calibrated is True
    assert meta.pi_calibrated is False

def test_arbitrum_medium_confidence():
    meta = chain_meta("arbitrum")
    assert meta.calibration_confidence == "MEDIUM"

def test_unknown_chain_returns_none_confidence():
    meta = chain_meta("unknown_chain")
    assert meta.calibration_confidence == "NONE"
    assert meta.is_actionable() is False


# ──────────────────────────────────────────────────────────────
# Stale policy
# ──────────────────────────────────────────────────────────────

def test_ok_status_returns_ok():
    assert stale_action("OK", 100) == "ok"

def test_stale_under_2h_returns_caution():
    assert stale_action("STALE", STALE_THRESHOLD_S + 100) == "caution"

def test_stale_over_2h_returns_wait():
    assert stale_action("STALE", STALE_WAIT_S + 1) == "wait"

def test_stale_at_boundary():
    assert stale_action("STALE", STALE_WAIT_S) == "wait"
    assert stale_action("STALE", STALE_WAIT_S - 1) == "caution"


# ──────────────────────────────────────────────────────────────
# ProofOfExecutionContext
# ──────────────────────────────────────────────────────────────

def test_pattern_key_composite():
    proof = ProofOfExecutionContext(l1_regime="S1D2", l2_regime="S1D1", bridge_state="BS1")
    assert proof.pattern_key == "S1D2×S1D1×BS1"

def test_pattern_key_l1_only():
    proof = ProofOfExecutionContext(l1_regime="S2D1", l2_regime=None, bridge_state="BS1")
    assert proof.pattern_key == "S2D1×NULL×BS1"

def test_bridge_is_placeholder():
    proof = ProofOfExecutionContext(l1_regime="S1D1", l2_regime="S1D1", bridge_state="BS1")
    assert proof.bridge_is_placeholder is True


# ──────────────────────────────────────────────────────────────
# Client parsing — from mock API response
# ──────────────────────────────────────────────────────────────

MOCK_L1_RESPONSE = {
    "chain": "ethereum",
    "oracle_status": "OK",
    "version": "v2",
    "structural": {"rhythm_ratio": 1.02, "continuity_ratio": 0.99},
    "execution_profile": {"index_a": 1.05, "index_b": 1.12, "index_c": 0.98},
    "divergence_index": -0.03,
    "regime": "S1D1",
    "data_age_seconds": 300,
    "issued_at": "2026-03-27T10:00:00Z",
    "expires_at": "2026-03-27T11:00:00Z",
    "l2_verified": True,
    "signature": "inv_sig_abc123def456ghi7",
}

def test_parse_l1_from_mock():
    client = InvariansClient(api_key="inv_test")
    attestation = client._parse_l1(MOCK_L1_RESPONSE, "ethereum")
    assert attestation.regime == "S1D1"
    assert attestation.chain == "ethereum"
    assert attestation.structural.rhythm_ratio == pytest.approx(1.02)
    assert attestation.stale_action == "ok"
    assert attestation.meta is not None
    assert attestation.meta.is_actionable() is True
    assert attestation.is_actionable() is True

def test_parse_l1_stale():
    stale_response = {**MOCK_L1_RESPONSE, "oracle_status": "STALE", "data_age_seconds": 5000}
    client = InvariansClient(api_key="inv_test")
    attestation = client._parse_l1(stale_response, "ethereum")
    assert attestation.stale_action == "caution"
    assert attestation.is_actionable() is False

def test_stale_policy_raise():
    stale_response = {**MOCK_L1_RESPONSE, "oracle_status": "STALE", "data_age_seconds": 5000}
    client = InvariansClient(api_key="inv_test", stale_policy="raise")
    with pytest.raises(StaleError) as exc_info:
        client._parse_l1(stale_response, "ethereum")
    assert exc_info.value.chain == "ethereum"
    assert exc_info.value.data_age_seconds == 5000
