# Changelog — invarians-py

## 0.3.1 — 2026-04-29 — Bilateral regime codes (phase β)

- **`Regime` Literal extended from 4 to 15 values** to support the bilateral regime codes
  emitted by the panel API since v1.1.0:
  - L1 phase α legacy (still emitted on SOL, AVAX): `S1D1`, `S1D2`, `S2D1`, `S2D2`
  - L1 phase β extended (active on ETH, POL since 2026-04-29):
    - direction on demand axis: `S1D2+`, `S1D2-`, `S1D2±`
    - direction on structure axis: `S2+D1`, `S2-D1`
    - combined: `S2+D2+`, `S2+D2-`, `S2+D2±`, `S2-D2+`, `S2-D2-`, `S2-D2±`
  - L2 phase β extended (active on BASE, OP since 2026-04-29 — no `D2±` on single-dim demand):
    `S1D2+`, `S1D2-`, `S2+D1`, `S2-D1`, `S2+D2+`, `S2+D2-`, `S2-D2+`, `S2-D2-`
  - ARB stays phase α (sigma_ratio structurally degenerate on Arbitrum Nitro).
- Behaviour: clients on 0.3.x are forward-compatible with phase β codes. Generic clients
  doing a regex match on the legacy 4 values must update to support the 15 values.
- No breaking changes. Backward-compatible additive Literal expansion.

---

## 0.3.0 — 2026-04-29 — Long-term EMA + shifts (API v1.1.0)

- **New `StructuralSlow` dataclass** exposing `rhythm_ratio_slow` and `continuity_ratio_slow`
  (~30-day EMA baseline) on L1 and L2 entries.
- **New `Shifts` dataclass** exposing `rhythm_shift` and `continuity_shift` (delta between
  short-term ~10h and long-term ~30d EMAs) — captures structural drift over time. Validates
  the article thesis "what is nominal is not fixed" published 2026-04-28.
- `L1Entry.structural_slow`, `L1Entry.shifts`, `L2Entry.structural_slow`, `L2Entry.shifts`
  added as `Optional` fields with default `None`. Backward-compatible with v1.0.x API.
- `parse_l1` / `parse_l2` populate the new fields when present in the API response.
- API version 1.1.0 is fully supported; v1.0.x clients reading 1.1.0 responses ignore the
  new fields silently.

---

## 0.2.1 — 2026-04-20 — README sync

- **README rewritten for Panel API.** The 0.2.0 release shipped with the legacy 0.1.x README
  by mistake, so every snippet on PyPI still used `get_execution_context()` — which raises
  `NotImplementedError` in 0.2.x. 0.2.1 ships the correct `get_panel()` / `verify_panel()` /
  `panel.bridge_by_id(...)` examples, the full per-item `status` table (`OK` / `STALE` /
  `UNAVAILABLE` / `UNCALIBRATED`), the native-bridge canonical IDs, and the P0→P3 calibration
  timeline.
- No code changes. Behaviour strictly identical to 0.2.0.

---

## 0.2.0 — 2026-04-20 — **Panel API (breaking change)**

### Pivot : direction-agnostic panel

The Invarians API now exposes a **single panel endpoint** returning the complete state
of all tracked L1 chains, L2 chains, and bridges. The AI agent composes its routes
client-side; the API no longer accepts `from`/`to` parameters.

### New — `get_panel()` + panel models
- `InvariansClient.get_panel(chains=None, bridges=None) -> PanelResponse`
  - Optional filters on chain names and/or bridge types
- New dataclasses: `PanelResponse`, `L1Entry`, `L2Entry`, `BridgeEntry`, `Coverage`,
  `SignedExecutionContext`
- Helpers: `panel.l1_by_chain(chain)`, `panel.l2_by_chain(chain)`, `panel.bridge_by_id(id)`,
  `panel.is_fully_ok`
- Per-item `status`: `OK | STALE | UNAVAILABLE | UNCALIBRATED`
- Per-item timestamps: `computed_at` (L1/L2), `observed_at` (bridges)
- Global `oracle_status`: `OK | DEGRADED`
- `signed_execution_context`: `payload_hash` (SHA-256 of canonical JSON), `signature`
  (HMAC-SHA256), `key_id` (`invarians-v1`), `anchor` (`None` in V1; populated in V1.1+
  with on-chain Merkle anchor on Arbitrum, targeted May 2026)

### New — `verify_panel(payload, signature)`
- Replaces `verify(attestation_payload)`: takes the panel dict and the signature
  string, recomputes HMAC server-side over canonical JSON (with
  `signed_execution_context` stripped), and returns a boolean.

### Breaking — Deprecated methods
- `get_l1()`, `get_l2()`, `get_execution_context()`, and `verify()` now raise
  `NotImplementedError` with a migration hint. The underlying endpoints return
  HTTP 410 Gone on the server side.
- Legacy dataclasses (`L1Attestation`, `L2Attestation`,
  `ExecutionContextAttestation`, `ProofOfExecutionContext`) are kept for import
  compatibility but are no longer populated by any client method.

### Migration
```python
# Before (v0.1.x)
ctx = client.get_execution_context(l1="ethereum", l2="arbitrum")
print(ctx.proof.l1_regime, ctx.proof.l2_regime, ctx.proof.bridge_state)

# After (v0.2.x)
panel = client.get_panel()
eth   = panel.l1_by_chain("ethereum")
arb   = panel.l2_by_chain("arbitrum")
br    = panel.bridge_by_id("arbitrum-ethereum/native")
print(eth.regime, arb.regime, br.state)  # agent composes the route itself
```

---

## 0.1.3 — 2026-04-02

### Calibration metadata
- **L2 chains downgraded from MEDIUM to LOW** : `arbitrum`, `base`, `optimism` are now marked
  `calibration_confidence="LOW"`. τ is structurally dormant on all active rollups (sequencer
  fixed cadence — S2D1/S2D2 unreachable until Phase D). π baselines converging until 25 Apr 2026.
  `is_actionable()` was already returning `False` for all L2 chains (blocked by `m1_validated=False`);
  this change aligns `calibration_confidence` with the actual signal reliability.
- Notes updated with explicit "Full calibration 25 Apr 2026" per chain.

---

## 0.1.2 — 2026-04-02

### Bug fixes
- **`_parse_l2` — silent S1D1 default corrected** : The standalone `/attestation/l2/{chain}`
  endpoint returns `l2_regime` (not `regime`). The parser was falling back to `"S1D1"` on
  every `get_l2()` call regardless of the actual oracle value. Fixed lookup order:
  `regime` → `l2_regime` → `state` → `"S1D1"`.

### New fields
- **`ExecutionProfile`** : Added `index_d` through `index_h` as `Optional[float]` (default `None`).
  These correspond to L2 extended signals (composition µ and adaptation σ) returned by the oracle
  but previously silently dropped. All `null` until Phase A/B/C calibration (~25 April 2026).
- **`L2Attestation`** : Added `tau_computed_at` and `pi_computed_at` as `Optional[str]` (default
  `None`). These timestamps are returned by `/attestation/l2/{chain}` (standalone only — not
  present in the `l2` block of `/attestation/execution-context`).

### Internal
- `__version__` in `__init__.py` aligned with `pyproject.toml` (was `0.1.0`, now `0.1.2`).

---

## 0.1.1 — 2026-04-01

Initial public release on PyPI.

- `InvariansClient` with `get_l1()`, `get_l2()`, `get_execution_context()`, `verify()`
- HTTP layer with retry (httpx or requests, user choice)
- `L1Attestation`, `L2Attestation`, `ExecutionContextAttestation`, `ProofOfExecutionContext`
- `ChainMeta` with calibration confidence per chain
- Stale policy (`ok` / `caution` / `wait`)
- `pattern_key` (`S1D1×S1D1×BS1`), `bridge_is_placeholder`
- Custom exceptions: `AuthError`, `RateLimitError`, `StaleError`, `ServerError`
