"""Invarians SDK — Client"""

from __future__ import annotations

import time
import logging
from typing import Optional
from urllib.parse import urljoin

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from .exceptions import AuthError, NotFoundError, RateLimitError, ServerError, StaleError
from .models import (
    L1Attestation, L2Attestation, ExecutionContextAttestation,
    StructuralSignals, ExecutionProfile, BeaconData, ProofOfExecutionContext,
    chain_meta, stale_action,
)

logger = logging.getLogger("invarians")

DEFAULT_BASE_URL = "https://sdpilypwumxsyyipceew.supabase.co/functions/v1/attestation"

# Retry defaults
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 1.5   # seconds


class InvariansClient:
    """
    Invarians Oracle API client — v0.1

    Usage:
        client = InvariansClient(api_key="inv_your_key_here")
        attestation = client.get_l1("ethereum")
        print(attestation.regime, attestation.stale_action)

    Parameters:
        api_key       : Bearer token (inv_...)
        base_url      : Override production URL (for testing)
        max_retries   : Number of retries on transient errors (default 3)
        stale_policy  : 'ok' (return data) | 'raise' (raise StaleError)
        timeout       : HTTP timeout in seconds (default 10)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        stale_policy: str = "ok",
        timeout: float = 10.0,
    ):
        if not api_key or not api_key.startswith("inv_"):
            raise AuthError("API key must start with 'inv_'. Get a key at invarians.com.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._stale_policy = stale_policy
        self._timeout = timeout

        if not _HAS_HTTPX and not _HAS_REQUESTS:
            raise ImportError(
                "invarians requires either 'httpx' or 'requests'. "
                "Install with: pip install invarians[requests] or pip install invarians[httpx]"
            )

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    def get_l1(self, chain: str) -> L1Attestation:
        """
        Fetch L1 chain state.

        Args:
            chain: 'ethereum' | 'polygon' | 'solana' | 'avalanche'

        Returns:
            L1Attestation with regime (S1D1/S1D2/S2D1/S2D2),
            structural signals, demand profile, and stale action.
        """
        data = self._get(f"/{chain}")
        return self._parse_l1(data, chain)

    def get_l2(self, chain: str) -> L2Attestation:
        """
        Fetch L2 chain state.

        Args:
            chain: 'arbitrum' | 'base' | 'optimism'

        Returns:
            L2Attestation with regime and signal quality metadata.
        """
        data = self._get(f"/l2/{chain}")
        return self._parse_l2(data, chain)

    def get_execution_context(self, l1: str = "ethereum", l2: str = "arbitrum") -> ExecutionContextAttestation:
        """
        Fetch composite L1×L2 execution context.

        Args:
            l1: L1 chain (default: 'ethereum')
            l2: L2 chain (default: 'arbitrum')

        Returns:
            ExecutionContextAttestation with proof_of_execution_context
            (l1_regime × l2_regime × bridge_state) and per-chain details.
        """
        data = self._get("/execution-context", params={"from": l1, "to": l2})
        return self._parse_execution_context(data)

    def verify(self, attestation_payload: dict) -> bool:
        """
        Verify an attestation signature via the oracle /verify endpoint.

        Args:
            attestation_payload: The full attestation dict as received from the API.

        Returns:
            True if signature is valid and attestation is not expired.
        """
        resp = self._post("/verify", json=attestation_payload)
        return resp.get("valid", False)

    # ──────────────────────────────────────────────────────────
    # HTTP layer
    # ──────────────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        url = self._base_url + path
        headers = {"Authorization": f"Bearer {self._api_key}"}

        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                raw = self._http_get(url, headers=headers, params=params)
                return raw
            except (ServerError, ConnectionError, TimeoutError) as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    wait = DEFAULT_BACKOFF_BASE ** attempt
                    logger.warning(
                        "Invarians API error (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1, self._max_retries, exc, wait
                    )
                    time.sleep(wait)
            except (AuthError, NotFoundError, RateLimitError):
                raise  # Don't retry auth/client errors

        raise last_exc or ServerError("All retries exhausted")

    def _post(self, path: str, json: dict) -> dict:
        url = self._base_url + path
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        return self._http_post(url, headers=headers, json=json)

    def _http_get(self, url: str, headers: dict, params: Optional[dict]) -> dict:
        if _HAS_HTTPX:
            import httpx
            resp = httpx.get(url, headers=headers, params=params, timeout=self._timeout)
        else:
            import requests
            resp = requests.get(url, headers=headers, params=params, timeout=self._timeout)
        return self._handle_response(resp)

    def _http_post(self, url: str, headers: dict, json: dict) -> dict:
        if _HAS_HTTPX:
            import httpx
            resp = httpx.post(url, headers=headers, json=json, timeout=self._timeout)
        else:
            import requests
            resp = requests.post(url, headers=headers, json=json, timeout=self._timeout)
        return self._handle_response(resp)

    def _handle_response(self, resp) -> dict:
        status = resp.status_code
        if status == 401:
            raise AuthError("Invalid API key. Check your inv_* token.")
        if status == 404:
            raise NotFoundError(f"Endpoint not found or chain not supported: {resp.url}")
        if status == 429:
            raise RateLimitError("Daily API quota exceeded. Free tier: 20 req/day.")
        if status >= 500:
            raise ServerError(f"Oracle server error {status}: {resp.text[:200]}")
        if status >= 400:
            raise ServerError(f"Client error {status}: {resp.text[:200]}")
        return resp.json()

    # ──────────────────────────────────────────────────────────
    # Parsers
    # ──────────────────────────────────────────────────────────

    def _parse_l1(self, data: dict, chain: str) -> L1Attestation:
        struct = data.get("structural", {})
        profile = data.get("execution_profile", {})
        beacon_raw = data.get("beacon")

        attestation = L1Attestation(
            chain=data.get("chain", chain),
            oracle_status=data.get("oracle_status", "OK"),
            regime=data.get("regime", data.get("state", "S1D1")),  # v4.2 renamed state→regime
            structural=StructuralSignals(
                rhythm_ratio=struct.get("rhythm_ratio", 0.0),
                continuity_ratio=struct.get("continuity_ratio", 0.0),
            ),
            execution_profile=ExecutionProfile(
                index_a=profile.get("index_a", 0.0),
                index_b=profile.get("index_b", 0.0),
                index_c=profile.get("index_c", 0.0),
            ),
            divergence_index=data.get("divergence_index", 0.0),
            data_age_seconds=data.get("data_age_seconds", 0.0),
            issued_at=data.get("issued_at", ""),
            expires_at=data.get("expires_at", ""),
            signature=data.get("signature", ""),
            version=data.get("version", "v2"),
            l2_verified=data.get("l2_verified", False),
            beacon=BeaconData(
                participation=beacon_raw.get("participation"),
                epoch=beacon_raw.get("epoch"),
                age_seconds=beacon_raw.get("age_seconds"),
            ) if beacon_raw else None,
            meta=chain_meta(chain),
        )

        self._apply_stale_policy(attestation.oracle_status, attestation.data_age_seconds, chain)
        return attestation

    def _parse_l2(self, data: dict, chain: str) -> L2Attestation:
        struct = data.get("structural", {})
        profile = data.get("execution_profile", {})

        attestation = L2Attestation(
            chain=data.get("chain", chain),
            oracle_status=data.get("oracle_status", "OK"),
            regime=data.get("regime", data.get("state", "S1D1")),
            structural=StructuralSignals(
                rhythm_ratio=struct.get("rhythm_ratio", 0.0),
                continuity_ratio=struct.get("continuity_ratio", 0.0),
            ),
            execution_profile=ExecutionProfile(
                index_a=profile.get("index_a", 0.0),
                index_b=profile.get("index_b", 0.0),
                index_c=profile.get("index_c", 0.0),
            ),
            data_age_seconds=data.get("data_age_seconds", 0.0),
            issued_at=data.get("issued_at", ""),
            expires_at=data.get("expires_at", ""),
            signature=data.get("signature", ""),
            meta=chain_meta(chain),
        )

        self._apply_stale_policy(attestation.oracle_status, attestation.data_age_seconds, chain)
        return attestation

    def _parse_execution_context(self, data: dict) -> ExecutionContextAttestation:
        poc = data.get("proof_of_execution_context", {})
        l1_raw = data.get("l1", {})
        l2_raw = data.get("l2")
        bridge_raw = data.get("bridge", {})

        l1_chain = l1_raw.get("chain", "ethereum")
        l2_chain = l2_raw.get("chain") if l2_raw else None

        l1 = self._parse_l1({**l1_raw, "oracle_status": data.get("oracle_status", "OK"),
                              "issued_at": data.get("issued_at", ""),
                              "expires_at": data.get("expires_at", ""),
                              "signature": data.get("signature", ""),
                              "divergence_index": l1_raw.get("divergence_index", 0.0)}, l1_chain)

        l2 = None
        if l2_raw and l2_chain:
            l2 = self._parse_l2({**l2_raw, "oracle_status": data.get("oracle_status", "OK"),
                                  "issued_at": data.get("issued_at", ""),
                                  "expires_at": data.get("expires_at", ""),
                                  "signature": data.get("signature", "")}, l2_chain)

        bridge_calibrated = (
            data.get("bridge_calibrated")
            or bridge_raw.get("calibrated", False)
        )

        return ExecutionContextAttestation(
            oracle_status=data.get("oracle_status", "OK"),
            proof=ProofOfExecutionContext(
                l1_regime=poc.get("l1_regime", poc.get("l1_state", l1.regime)),
                l2_regime=poc.get("l2_regime", poc.get("l2_state")) if l2 else None,
                bridge_state=poc.get("bridge_state", "BS1"),
                bridge_calibrated=bridge_calibrated,
            ),
            l1=l1,
            l2=l2,
            bridge_state=bridge_raw.get("state", "BS1"),
            signature=data.get("signature", ""),
        )

    def _apply_stale_policy(self, oracle_status: str, data_age_seconds: float, chain: str):
        if self._stale_policy == "raise" and oracle_status == "STALE":
            raise StaleError(chain, data_age_seconds)
