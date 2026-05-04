# invarians-py

**Cross-chain infrastructure context for autonomous agents. Three primitives in one signed payload: Attestation, Regime, Shift.**

L2 activity no longer shows up in L1 gas fees. Sequencer slowdowns and bridge delays leave no economic trace. Fee monitors stay silent. Invarians detects them.

Since v0.6.0 (2026-05-04), the SDK targets the production endpoint at `https://api.invarians.com` and exposes the v2.0 panel: a single direction-agnostic payload with axis-grouped metric blocks, drift signals, and 12 signed regime codes per chain.

```python
from invarians import InvariansClient

client = InvariansClient(api_key="inv_your_key_here")
panel  = client.get_panel_v2(include="diagnostic")

eth = panel.l1_by_chain("ethereum")
arb = panel.l2_by_chain("arbitrum")
br  = panel.bridge_by_id("arbitrum-ethereum/native")

# Regime: 12 signed codes (S1D1, S1D2+, S1D2-, S1D2±, S2+D1, S2-D1, S2+D2+, ...)
if eth.regime and (eth.regime.startswith("S2") or eth.regime.endswith("D2-")):
    pause_agent_execution()

# Drift: per-axis composite trend, plus per-metric shift
if eth.drift.demand_magnitude_delta is not None and eth.drift.demand_magnitude_delta > 0:
    log.info("Demand axis deviation amplifying on ethereum")

print(panel.oracle_status)        # "OK" | "DEGRADED"
print(eth.regime, eth.status)     # e.g. "S1D1" "OK"
print(br.state, br.calibrated)    # e.g. "BS1" True
```

---

## Install

```bash
pip install invarians[requests]  # default
pip install invarians[httpx]     # async-friendly
```

Requires Python 3.9+. Get an API key at [invarians.com](https://invarians.com).

---

## The three primitives

The v2.0 panel separates three independent concerns. Every panel response carries all three.

### 1. Attestation (HMAC integrity)

Every panel response carries a `signed_execution_context` with `payload_hash`, `signature`, `key_id`, and an optional on-chain `anchor`. Independently verifiable.

```python
panel = client.get_panel_v2()
sec   = panel.signed_execution_context

ok = client.verify_panel_v2(panel_raw_dict, sec.signature)
# True if HMAC matches the canonical JSON of the payload
```

### 2. Regime (12 signed codes per chain)

Per-chain regime is a 2-axis tuple on the SxDx grid. Structure axis: `S1` nominal, `S2+` structural high, `S2-` structural low. Demand axis: `D1` nominal, `D2+` demand high, `D2-` demand low, `D2±` composition split. Twelve codes total per chain on both L1 and L2.

```python
eth = panel.l1_by_chain("ethereum")

if eth.regime == "S2+D1":
    # Structural high stress, demand nominal
    return {"action": "hold", "reason": eth.regime}
elif eth.regime and eth.regime.startswith("S1") and not eth.regime.endswith("D1"):
    # Nominal infrastructure, asymmetric or elevated demand
    proceed_with_caution()
```

### 3. Shift (drift signal)

Each metric block exposes `ratio` (current state vs short EMA), `ratio_long` (current vs long EMA), `shift` (deviation magnitude), `shift_delta` (raw direction), `shift_magnitude_delta` (deviation amplifying or shrinking). Plus a per-axis composite drift on every chain entry.

```python
eth = panel.l1_by_chain("ethereum")

# Per-axis composite drift
print(eth.drift.demand)                     # composite drift magnitude on demand axis
print(eth.drift.demand_magnitude_delta)     # > 0 amplifying, < 0 reverting

# Per-metric shift (diagnostic mode only)
print(eth.demand.tx.shift)                  # per-metric tx-count shift
print(eth.structural.rhythm.shift)          # per-metric rhythm shift
```

Trend reading rule for an agent in an active regime:

| `shift_magnitude_delta` | Interpretation |
|---|---|
| `> 0` | Deviation amplifying. Regime persists or worsens. |
| `< 0` | Deviation shrinking. Regime exit toward nominal likely. |
| `≈ 0` | Regime stable. |

---

## Common patterns

### Hold on structural stress

```python
panel = client.get_panel_v2()
eth   = panel.l1_by_chain("ethereum")

if eth.regime and eth.regime.startswith("S2"):
    # Structural stress, regardless of polarity (S2+ or S2-)
    return {"action": "hold", "reason": eth.regime}
```

### Detect silent slowdown (no fee signal)

S2+D1 and S2-D1 are the codes where infrastructure degrades without any demand signature. Fee monitors stay silent.

```python
eth = client.get_panel_v2().l1_by_chain("ethereum")

if eth.regime in ("S2+D1", "S2-D1"):
    # No gas spike, no price move, but the chain is structurally stressed
    alert_ops(f"Silent stress on ethereum: {eth.regime}")
```

### Certify execution conditions on chain

```python
panel = client.get_panel_v2()
sec   = panel.signed_execution_context

if panel.oracle_status == "OK":
    result = execute_trade(...)
    audit_log.append({
        "tx":            result.hash,
        "panel_version": panel.version,           # "2.0.0"
        "issued_at":     panel.issued_at,
        "payload_hash":  sec.payload_hash,        # "0x{sha256}"
        "signature":     sec.signature,           # "hmac-sha256:{hex}"
        "key_id":        sec.key_id,
        "anchor":        sec.anchor,              # on-chain anchor slot when available
    })
```

### Route around bridge stress

Bridge IDs are canonical: `{chainA}-{chainB}/{type}`. Three native bridges live, ten CCIP lanes and ten CCTP routes calibrate mid-May 2026.

```python
panel = client.get_panel_v2(bridges=["native", "ccip", "cctp"])

br = panel.bridge_by_id("arbitrum-ethereum/native")
if br and br.calibrated and br.state == "BS2":
    use_fallback_bridge()

# CCIP / CCTP entries during their pre-calibration window expose raw signals
ccip = next((b for b in panel.bridges if b.type == "ccip" and not b.calibrated), None)
if ccip and ccip.commit_latency_p90_s and ccip.commit_latency_p90_s > 600:
    log.warning(f"{ccip.id}: commit latency P90 {ccip.commit_latency_p90_s:.0f}s")
```

### Handle degraded data gracefully

```python
panel = client.get_panel_v2()

if panel.oracle_status == "DEGRADED":
    for entry in panel.l1 + panel.l2:
        if entry.status != "OK":
            log.warning(f"{entry.chain}: {entry.status}")
    for br in panel.bridges:
        if br.status in ("STALE", "UNAVAILABLE"):
            log.warning(f"{br.id}: {br.status}")
    fall_back_to_conservative_mode()
```

Per-item status values:

| Status | Meaning |
|---|---|
| `OK` | Signal fresh and calibrated |
| `STALE` | Last update older than the freshness window (1h for L1/L2, 10m for bridges) |
| `UNAVAILABLE` | Signal temporarily missing |
| `UNCALIBRATED` | Collector running, thresholds not yet published. Does not trigger `DEGRADED`. |

---

## Regime grid

12 signed codes per chain on both L1 and L2.

| Code | Structure | Demand | What it captures |
|---|---|---|---|
| `S1D1` | nominal | nominal | Within calibrated norms |
| `S1D2+` | nominal | high | Demand surge, infrastructure healthy |
| `S1D2-` | nominal | low | Demand depressed, infrastructure healthy |
| `S1D2±` | nominal | split | Asymmetric demand composition |
| `S2+D1` | high stress | nominal | Silent structural slowdown. No fee signal. |
| `S2-D1` | low stress | nominal | Silent structural underrun. No fee signal. |
| `S2+D2+` | high stress | high | Combined upward stress |
| `S2+D2-` | high stress | low | Stress with depressed demand |
| `S2+D2±` | high stress | split | Stress with asymmetric demand |
| `S2-D2+` | low stress | high | Underrun with elevated demand |
| `S2-D2-` | low stress | low | Underrun with depressed demand |
| `S2-D2±` | low stress | split | Underrun with asymmetric demand |

Bridge states:

| Code | Type | Meaning |
|---|---|---|
| `BS1` | native | Batches posted within calibrated cadence (P97/30d threshold) |
| `BS2` | native | Posting latency above threshold |
| `CS1`, `CS2` | CCIP | Cross-chain lane within / above its calibrated thresholds (calibrating ~2026-05-20) |
| `TS1`, `TS2` | CCTP | Transfer route within / above its calibrated thresholds (calibrating ~2026-05-20) |
| `null` | any | Not yet calibrated. Raw signals still exposed on the entry. |

---

## Chain coverage

| Chain | Layer | Confidence | Status |
|---|---|---|---|
| ethereum | L1 | HIGH | live |
| polygon | L1 | MEDIUM | live |
| arbitrum | L2 | MEDIUM | live |
| base | L2 | MEDIUM | live |
| optimism | L2 | MEDIUM | live |
| avalanche | L1 | LOW | observation |
| solana | L1 | LOW | calibration target Q3 2026 |

Bridges live: 3 native (ARB / BASE / OP to ETH), 10 CCIP lanes, 10 CCTP routes. CCIP and CCTP enter classified mode after the P97/30d threshold is committed (target mid-May 2026).

---

## Migrating from v0.5.x

The v1.0 panel methods are removed in v0.6.0 and now raise `NotImplementedError`. Two methods remain: `get_panel_v2` and `verify_panel_v2`.

```python
# Before (v0.5.x)
panel = client.get_panel(chains=["ethereum"])
ok    = client.verify_panel(panel_raw, signature)

# After (v0.6.0)
panel = client.get_panel_v2(chains=["ethereum"], include="diagnostic")
ok    = client.verify_panel_v2(panel_raw, signature)
```

The default base URL changes from the raw Supabase Edge Function URL to `https://api.invarians.com`, the production endpoint hardened with origin checks, request timeouts, and server-side credentials.

---

## Error handling

```python
from invarians.exceptions import AuthError, RateLimitError, ServerError

try:
    panel = client.get_panel_v2()
except AuthError:
    print("Invalid API key")
except RateLimitError:
    print("Quota exceeded. Free tier: 20 req/day")
except ServerError as e:
    print(f"Service unavailable: {e}")
```

---

## Documentation

API reference: [invarians.com/developers.html](https://invarians.com/developers.html)

---

## License

MIT
