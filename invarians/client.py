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
    # Panel API v1.0 (2026-04-20)
    PanelResponse, L1Entry, L2Entry, BridgeEntry, Coverage, SignedExecutionContext,
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

    def get_panel(
        self,
        chains: Optional[list] = None,
        bridges: Optional[list] = None,
    ) -> PanelResponse:
        """
        Fetch the full attestation panel (L1 states, L2 states, bridge states).

        The panel is direction-agnostic: the agent composes its routes
        client-side by picking L1/L2/bridge items from the panel.

        Args:
            chains:  Optional filter — e.g. ['ethereum','arbitrum','base']
            bridges: Optional filter by bridge type — e.g. ['native'] or ['native','ccip']

        Returns:
            PanelResponse with l1[], l2[], bridges[], coverage, and
            signed_execution_context (payload_hash + HMAC signature + anchor slot).
        """
        params: dict = {}
        if chains:
            params["chains"] = ",".join(chains)
        if bridges:
            params["bridges"] = ",".join(bridges)
        data = self._get("/panel", params=params or None)
        return self._parse_panel(data)

    def verify_panel(self, panel_payload: dict, signature: str) -> bool:
        """
        Verify the HMAC signature of a panel payload.

        The verify endpoint recomputes the HMAC over the canonical JSON of the
        panel payload (with `signed_execution_context` stripped) and compares.

        Args:
            panel_payload: The full panel dict as received from /panel.
                           The `signed_execution_context` field is stripped
                           server-side before recomputing the HMAC.
            signature:     The signature string to verify, e.g.
                           "hmac-sha256:{hex}" from payload's signed_execution_context.

        Returns:
            True if the signature matches.
        """
        resp = self._post("/verify", json={"payload": panel_payload, "signature": signature})
        return resp.get("valid", False)

    # ── Deprecated API (410 Gone since 2026-04-20) ─────────────
    def get_l1(self, chain: str) -> L1Attestation:
        """DEPRECATED — endpoint removed 2026-04-20. Use ``get_panel()``.

        The backend now returns 410 Gone. Migrate to:

            panel = client.get_panel()
            eth   = panel.l1_by_chain('ethereum')
        """
        raise NotImplementedError(
            "get_l1() is deprecated since 2026-04-20. "
            "Use client.get_panel() and panel.l1_by_chain(chain) instead."
        )

    def get_l2(self, chain: str) -> L2Attestation:
        """DEPRECATED — endpoint removed 2026-04-20. Use ``get_panel()``."""
        raise NotImplementedError(
            "get_l2() is deprecated since 2026-04-20. "
            "Use client.get_panel() and panel.l2_by_chain(chain) instead."
        )

    def get_execution_context(self, l1: str = "ethereum", l2: str = "arbitrum") -> ExecutionContextAttestation:
        """DEPRECATED — endpoint removed 2026-04-20. Compose routes client-side.

        Rationale: the API no longer exposes directional routes. A bridge is
        stressed (or not) regardless of flow direction. The agent picks L1, L2,
        and bridge states from the panel and composes its own route.
        """
        raise NotImplementedError(
            "get_execution_context() is deprecated since 2026-04-20. "
            "The API no longer exposes directional routes. "
            "Use client.get_panel() and compose routes client-side from l1[], l2[], bridges[]."
        )

    def verify(self, attestation_payload: dict) -> bool:
        """DEPRECATED — use ``verify_panel(panel_payload, signature)``."""
        raise NotImplementedError(
            "verify() is deprecated since 2026-04-20. "
            "Use client.verify_panel(panel_payload, signature) for the new panel API."
        )

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
            regime=data.get("regime", data.get("l2_regime", data.get("state", "S1D1"))),
            structural=StructuralSignals(
                rhythm_ratio=struct.get("rhythm_ratio", 0.0),
                continuity_ratio=struct.get("continuity_ratio", 0.0),
            ),
            execution_profile=ExecutionProfile(
                index_a=profile.get("index_a", 0.0),
                index_b=profile.get("index_b", 0.0),
                index_c=profile.get("index_c", 0.0),
                index_d=profile.get("index_d"),
                index_e=profile.get("index_e"),
                index_f=profile.get("index_f"),
                index_g=profile.get("index_g"),
                index_h=profile.get("index_h"),
            ),
            data_age_seconds=data.get("data_age_seconds", 0.0),
            issued_at=data.get("issued_at", ""),
            expires_at=data.get("expires_at", ""),
            signature=data.get("signature", ""),
            tau_computed_at=data.get("tau_computed_at"),
            pi_computed_at=data.get("pi_computed_at"),
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

    # ──────────────────────────────────────────────────────────
    # Panel API parser (v1.0 — 2026-04-20)
    # ──────────────────────────────────────────────────────────

    def _parse_panel(self, data: dict) -> PanelResponse:
        panel_raw = data.get("panel", {})

        def parse_l1(raw: dict) -> L1Entry:
            struct = raw.get("structural", {}) or {}
            profile = raw.get("execution_profile", {}) or {}
            chain = raw.get("chain", "")
            return L1Entry(
                chain=chain,
                regime=raw.get("regime"),
                status=raw.get("status", "UNAVAILABLE"),
                computed_at=raw.get("computed_at"),
                window=raw.get("window", "1h"),
                divergence_index=raw.get("divergence_index"),
                structural=StructuralSignals(
                    rhythm_ratio=struct.get("rhythm_ratio") or 0.0,
                    continuity_ratio=struct.get("continuity_ratio") or 0.0,
                ),
                execution_profile=ExecutionProfile(
                    index_a=profile.get("index_a") or 0.0,
                    index_b=profile.get("index_b") or 0.0,
                    index_c=profile.get("index_c") or 0.0,
                ),
                meta=chain_meta(chain) if chain else None,
            )

        def parse_l2(raw: dict) -> L2Entry:
            struct = raw.get("structural", {}) or {}
            profile = raw.get("execution_profile", {}) or {}
            chain = raw.get("chain", "")
            return L2Entry(
                chain=chain,
                regime=raw.get("regime"),
                status=raw.get("status", "UNAVAILABLE"),
                computed_at=raw.get("computed_at"),
                window=raw.get("window", "1h"),
                structural=StructuralSignals(
                    rhythm_ratio=struct.get("rhythm_ratio") or 0.0,
                    continuity_ratio=struct.get("continuity_ratio") or 0.0,
                ),
                execution_profile=ExecutionProfile(
                    index_a=profile.get("index_a") or 0.0,
                    index_b=profile.get("index_b") or 0.0,
                    index_c=profile.get("index_c") or 0.0,
                    index_d=profile.get("index_d"),
                    index_e=profile.get("index_e"),
                    index_f=profile.get("index_f"),
                    index_g=profile.get("index_g"),
                    index_h=profile.get("index_h"),
                ),
                meta=chain_meta(chain) if chain else None,
            )

        def parse_bridge(raw: dict) -> BridgeEntry:
            return BridgeEntry(
                id=raw.get("id", ""),
                endpoints=list(raw.get("endpoints", []) or []),
                type=raw.get("type", "native"),
                state=raw.get("state"),
                calibrated=bool(raw.get("calibrated", False)),
                status=raw.get("status", "UNAVAILABLE"),
                observed_at=raw.get("observed_at"),
                window=raw.get("window", "10m"),
                last_batch_age_seconds=raw.get("last_batch_age_seconds"),
                # CCIP raw signals (present in P2+ for type=="ccip")
                last_sequence_advance_seconds=raw.get("last_sequence_advance_seconds"),
                sequence_gap=raw.get("sequence_gap"),
                commit_latency_p90_s=raw.get("commit_latency_p90_s"),
                execute_latency_p90_s=raw.get("execute_latency_p90_s"),
                total_latency_p90_s=raw.get("total_latency_p90_s"),
                rmn_cursed=raw.get("rmn_cursed"),
                # CCTP raw signals (present in P2+ for type=="cctp")
                attestation_latency_p90_s=raw.get("attestation_latency_p90_s"),
                attestation_latency_p99_s=raw.get("attestation_latency_p99_s"),
                attestation_success_rate_1h=raw.get("attestation_success_rate_1h"),
                circle_api_status=raw.get("circle_api_status"),
            )

        cov_raw = data.get("coverage", {}) or {}
        coverage = Coverage(
            l1_chains=list(cov_raw.get("l1_chains", []) or []),
            l2_chains=list(cov_raw.get("l2_chains", []) or []),
            bridges_native=int(cov_raw.get("bridges_native", 0) or 0),
            bridges_ccip=int(cov_raw.get("bridges_ccip", 0) or 0),
            bridges_cctp=int(cov_raw.get("bridges_cctp", 0) or 0),
            methodology_url=cov_raw.get("methodology_url", ""),
        )

        sec_raw = data.get("signed_execution_context", {}) or {}
        sec = SignedExecutionContext(
            payload_hash=sec_raw.get("payload_hash", ""),
            signature=sec_raw.get("signature", ""),
            key_id=sec_raw.get("key_id", "invarians-v1"),
            anchor=sec_raw.get("anchor"),
        )

        return PanelResponse(
            version=data.get("version", "1.0.0"),
            oracle_status=data.get("oracle_status", "OK"),
            issued_at=data.get("issued_at", ""),
            l1=[parse_l1(e) for e in panel_raw.get("l1", [])],
            l2=[parse_l2(e) for e in panel_raw.get("l2", [])],
            bridges=[parse_bridge(b) for b in panel_raw.get("bridges", [])],
            coverage=coverage,
            signed_execution_context=sec,
        )
