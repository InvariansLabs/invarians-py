# invarians-py

  Invarians makes invisible blockchain infrastructure failures observable — before they show up in gas fees.

  L2 activity no longer shows up in L1 gas fees. Sequencer failures and bridge delays leave no economic trace. Fee monitors stay silent. Invarians detects
  them.

  from invarians import InvariansClient

  client = InvariansClient(api_key="inv_your_key_here")
  ctx = client.get_execution_context(l1="ethereum", l2="arbitrum")

  l2 = ctx.proof.l2_regime or ""
  if ctx.proof.l1_regime.startswith("S2") or l2.startswith("S2"):
      # Structural stress detected — L1, L2, or both
      # Invisible to fee monitors
      pause_agent_execution()

  print(ctx.proof.pattern_key)   # "S1D1×S1D2×BS1"
  print(ctx.is_actionable())     # True

  ---
  Install

  pip install invarians[requests]  # default
  pip install invarians[httpx]     # async-friendly

  Requires Python 3.9+. Get an API key at https://invarians.com.

  ---
  What you can do with it

  1. Pause execution when infrastructure degrades

  ctx = client.get_execution_context(l1="ethereum", l2="arbitrum")

  if ctx.proof.l1_regime.startswith("S2"):
      # Structural stress detected — hold until nominal
      return {"action": "hold", "reason": ctx.proof.l1_regime}

  2. Detect silent failures (S2D1)

  S2D1 is the critical regime: structural stress with no demand signature. A fee monitor reports normal while Invarians detects degradation.

  att = client.get_l1("ethereum")

  if att.regime == "S2D1":
      # Chain slowing — no gas spike, no price move
      # Nothing shows on any fee monitor
      alert_ops("S2D1 detected on Ethereum")

  3. Certify execution conditions (PoEC)

  Attach a signed attestation to every agent action for audit or dispute resolution.

  ctx = client.get_execution_context(l1="ethereum", l2="arbitrum")

  if ctx.is_actionable():
      result = execute_trade(...)
      audit_log.append({
          "tx": result.hash,
          "execution_context": ctx.proof.pattern_key,   # "S1D1×S1D1×BS1"
          "attestation": ctx.signature,
          "issued_at": ctx.l1.issued_at,
      })

  4. Adjust routing on bridge stress

  ctx = client.get_execution_context(l1="ethereum", l2="arbitrum")

  if ctx.proof.bridge_state == "BS2":
      # Bridge degraded — route via alternative path
      use_fallback_bridge()
  elif ctx.proof.l2_regime == "S1D2":
      # L2 demand elevated — expect higher fees
      adjust_slippage_tolerance(factor=1.3)

  5. Handle stale data gracefully

  att = client.get_l1("ethereum")

  match att.stale_action:
      case "ok":
          proceed()
      case "caution":
          proceed_with_reduced_size()
      case "wait":
          hold()   # Data > 2h old — do not act

  ---
  Regimes

  ┌──────┬───────────┬──────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Code │ Structure │  Demand  │                                                 What it means                                                 │
  ├──────┼───────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ S1D1 │ nominal   │ nominal  │ Infrastructure within calibrated norms                                                                        │
  ├──────┼───────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ S1D2 │ nominal   │ elevated │ Structurally sound, demand above baseline                                                                     │
  ├──────┼───────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ S2D1 │ stress    │ nominal  │ The only regime where the chain degrades silently — no gas spike, no price signal. Invisible to gas monitors. │
  ├──────┼───────────┼──────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ S2D2 │ stress    │ elevated │ Structural stress and elevated demand simultaneously                                                          │
  └──────┴───────────┴──────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  ---
  Signal quality

  Every response carries explicit calibration metadata. The SDK never hides uncertainty.

  att = client.get_l1("solana")

  print(att.meta.m1_validated)            # False — backtest not yet validated
  print(att.meta.calibration_confidence)  # "LOW"
  print(att.meta.notes)                   # "π not calibrated. τ only."
  print(att.is_actionable())              # False

  Chain coverage

  ┌───────────┬───────┬────────────┬──────────────┐
  │   Chain   │ Layer │ Confidence │    Ready     │
  ├───────────┼───────┼────────────┼──────────────┤
  │ ethereum  │ L1    │ MEDIUM     │ ✅           │
  ├───────────┼───────┼────────────┼──────────────┤
  │ polygon   │ L1    │ MEDIUM     │ ✅           │
  ├───────────┼───────┼────────────┼──────────────┤
  │ arbitrum  │ L2    │ MEDIUM     │ ✅           │
  ├───────────┼───────┼────────────┼──────────────┤
  │ base      │ L2    │ MEDIUM     │ ✅           │
  ├───────────┼───────┼────────────┼──────────────┤
  │ optimism  │ L2    │ MEDIUM     │ ✅           │
  ├───────────┼───────┼────────────┼──────────────┤
  │ solana    │ L1    │ LOW        │ ⏳ July 2026 │
  ├───────────┼───────┼────────────┼──────────────┤
  │ avalanche │ L1    │ NONE       │ ⏳ July 2026 │
  └───────────┴───────┴────────────┴──────────────┘

  ---
  Error handling

  from invarians.exceptions import AuthError, RateLimitError, ServerError

  try:
      att = client.get_l1("ethereum")
  except AuthError:
      print("Invalid API key")
  except RateLimitError:
      print("Quota exceeded — free tier: 20 req/day")
  except ServerError as e:
      print(f"Oracle unavailable: {e}")

  ---
  Verify an attestation

  ctx = client.get_execution_context(l1="ethereum", l2="arbitrum")
  valid = client.verify({"attestation": ctx.l1.__dict__, "signature": ctx.signature})
  print(valid)  # True

  ---
  Documentation

  API reference: https://invarians.com/developers.html

  ---
  License

  MIT
