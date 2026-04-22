# invarians-py

**Invarians makes invisible blockchain infrastructure failures observable — before they show up in gas fees.**

L2 activity no longer shows up in L1 gas fees. Sequencer failures and bridge delays leave no economic trace. Fee monitors stay silent. Invarians detects them.

Since **v0.2.0** (2026-04-20), the API is a **direction-agnostic panel**. A single call returns the current state of every tracked L1, L2, and bridge. The agent composes its own route client-side.

```python
from invarians import InvariansClient

client = InvariansClient(api_key="inv_your_key_here")
panel  = client.get_panel()

eth    = panel.l1_by_chain("ethereum")
arb    = panel.l2_by_chain("arbitrum")
bridge = panel.bridge_by_id("arbitrum-ethereum/native")

if eth.regime.startswith("S2") or (arb and arb.regime and arb.regime.startswith("S2")):
    # Structural stress detected — L1, L2, or both
    # Invisible to fee monitors
    pause_agent_execution()

print(panel.oracle_status)          # "OK" | "DEGRADED"
print(eth.regime, eth.status)       # "S1D1" "OK"
print(bridge.state, bridge.status)  # None "UNCALIBRATED"  (P0, native calibration lands 2026-04-22)
```

---

## Install

```bash
pip install invarians[requests]  # default
pip install invarians[httpx]     # async-friendly
```

Requires Python 3.9+. Get an API key at [invarians.com](https://invarians.com).

---

## What you can do with it

### 1. Pause execution when infrastructure degrades

```python
panel = client.get_panel()
eth   = panel.l1_by_chain("ethereum")

if eth.regime and eth.regime.startswith("S2"):
    # Structural stress detected — hold until nominal
    return {"action": "hold", "reason": eth.regime}
```

### 2. Detect silent failures (S2D1)

S2D1 is the critical regime: structural stress with no demand signature. A fee monitor reports normal while Invarians detects degradation.

```python
eth = client.get_panel().l1_by_chain("ethereum")

if eth.regime == "S2D1":
    # Chain slowing — no gas spike, no price move
    # Nothing shows on any fee monitor
    alert_ops("S2D1 detected on Ethereum")
```

### 3. Certify execution conditions

Every panel carries a signed attestation over its canonical JSON. Attach it to any agent action for audit or dispute resolution.

```python
panel = client.get_panel()

if panel.is_fully_ok:
    result = execute_trade(...)
    sec = panel.signed_execution_context
    audit_log.append({
        "tx":               result.hash,
        "panel_version":    panel.version,           # "1.0.0"
        "issued_at":        panel.issued_at,
        "payload_hash":     sec.payload_hash,        # "0x{sha256}"
        "signature":        sec.signature,           # "hmac-sha256:{hex}"
        "key_id":           sec.key_id,              # "invarians-v1"
        "anchor":           sec.anchor,              # None in V1, on-chain anchor from May 2026
    })
```

### 4. Route around bridge stress

Bridge IDs are canonical: `{chainA}-{chainB}/{type}` (e.g. `arbitrum-ethereum/native`). Three native bridges are exposed at launch; CCTP and CCIP lanes are added in the panel on 2026-04-24 (calibration lands ≥ 2026-05-23).

```python
panel  = client.get_panel()
bridge = panel.bridge_by_id("arbitrum-ethereum/native")

if bridge.state == "BS2":
    # Bridge degraded — route via alternative path
    use_fallback_bridge()
elif bridge.status == "UNCALIBRATED":
    # Raw signal still available — use with care
    age = bridge.last_batch_age_seconds
    if age is not None and age > 300:
        use_fallback_bridge()
```

### 5. Handle degraded data gracefully

`oracle_status` reports global health. Per-item `status` tells you exactly which signal is unreliable.

```python
panel = client.get_panel()

if panel.oracle_status == "DEGRADED":
    # At least one L1 / L2 / bridge is STALE or UNAVAILABLE
    for entry in panel.l1 + panel.l2:
        if entry.status != "OK":
            log.warning(f"{entry.chain}: {entry.status}")
    for bridge in panel.bridges:
        if bridge.status in ("STALE", "UNAVAILABLE"):
            log.warning(f"{bridge.id}: {bridge.status}")
    fall_back_to_conservative_mode()
```

Per-item status values:

| Status | Meaning |
|--------|---------|
| `OK` | Signal fresh and calibrated |
| `STALE` | Last update older than the freshness window (`1h` for L1/L2, `10m` for bridges) |
| `UNAVAILABLE` | Signal temporarily missing |
| `UNCALIBRATED` | Collector running, thresholds not yet published — does **not** trigger `DEGRADED` |

---

## Regimes

| Code | Structure | Demand | What it means |
|------|-----------|--------|---------------|
| S1D1 | nominal | nominal | Infrastructure within calibrated norms |
| S1D2 | nominal | elevated | Structurally sound, demand above baseline |
| **S2D1** | **stress** | **nominal** | **The only regime where the chain degrades silently — no gas spike, no price signal. Invisible to gas monitors.** |
| S2D2 | stress | elevated | Structural stress and elevated demand simultaneously |

Bridge states:

| Code | Type | Meaning |
|------|------|---------|
| `BS1` | native | Batches posted to L1 within calibrated cadence |
| `BS2` | native | Posting latency above P97/30d threshold |
| `null` | any | Not yet calibrated (raw `last_batch_age_seconds` still exposed) |

CCIP (`CS1/CS2`) and CCTP (`TS1/TS2`) states arrive in the panel on 2026-04-24 (UNCALIBRATED) and calibrate ≥ 2026-05-23.

---

## Signal quality

Every L1 and L2 entry is enriched with explicit calibration metadata. The SDK never hides uncertainty.

```python
sol = client.get_panel().l1_by_chain("solana")

print(sol.meta.m1_validated)            # False — backtest not yet validated
print(sol.meta.calibration_confidence)  # "LOW"
print(sol.meta.notes)                   # "π not calibrated. τ only."
```

### Chain coverage

| Chain | Layer | Confidence | Ready |
|-------|-------|------------|-------|
| ethereum | L1 | MEDIUM | ✅ |
| polygon | L1 | MEDIUM | ✅ |
| arbitrum | L2 | LOW | ⏳ 25 Apr 2026 |
| base | L2 | LOW | ⏳ 25 Apr 2026 |
| optimism | L2 | LOW | ⏳ 25 Apr 2026 |
| solana | L1 | LOW | ⏳ July 2026 |
| avalanche | L1 | NONE | ⏳ July 2026 |

Native bridges exposed at launch:

| Bridge ID | Type | Calibrated | Calibration date |
|-----------|------|------------|------------------|
| `arbitrum-ethereum/native` | native | ❌ | 2026-04-22 |
| `base-ethereum/native` | native | ❌ | 2026-04-22 |
| `optimism-ethereum/native` | native | ❌ | 2026-04-22 |

---

## Verify a panel

```python
panel     = client.get_panel()
payload   = panel_raw_dict                                      # as returned by the API
signature = panel.signed_execution_context.signature
valid     = client.verify_panel(payload, signature)
print(valid)  # True
```

---

## Error handling

```python
from invarians.exceptions import AuthError, RateLimitError, ServerError

try:
    panel = client.get_panel()
except AuthError:
    print("Invalid API key")
except RateLimitError:
    print("Quota exceeded — free tier: 20 req/day")
except ServerError as e:
    print(f"Service unavailable: {e}")
```

---

## Migrating from v0.1.x

The legacy endpoints (`/attestation/{chain}`, `/attestation/l2/{chain}`, `/attestation/execution-context`) return **HTTP 410 Gone** since 2026-04-20, and the matching SDK methods raise `NotImplementedError`:

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

## Documentation

API reference: [invarians.com/developers.html](https://invarians.com/developers.html)

---

## License

MIT
