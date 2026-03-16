# Workflow: Monte Carlo Financial Simulation

## Objective
Run probabilistic financial projections for investment and retirement scenarios using a
vectorized GBM (Geometric Brownian Motion) wealth process. Produces success probabilities,
percentile statistics, time-series fan chart data, and final-value histograms.

---

## Required Inputs
Either:
- **Scenario config JSON file** — matches the schema defined in Section 5 below, or
- **Web UI** — fill in the form at `http://localhost:8000` and click Run.

---

## Prerequisites

```bash
# Install dependencies (one-time)
pip install -r requirements.txt
```

Dependencies: `numpy`, `fastapi`, `uvicorn`, `scipy`, `python-multipart`

---

## Steps

### Option A — Web UI (recommended)

1. Start the server:
   ```bash
   python tools/api_server.py
   ```
2. Open `http://localhost:8000` in your browser.
3. Fill in the five input groups: **Timeline**, **Money & Resources**, **Risk & Volatility**,
   **Success Criteria**, **Advanced**.
4. Optionally add shock events (e.g., market crash probability and impact).
5. Click **Run Simulation**.
6. Review the fan chart, histogram, KPI cards, and percentile table.
7. Click **Save Scenario** to download the config JSON for reproducibility.
8. Click **Download Results JSON** to export the full results.

---

### Option B — CLI (headless / automation)

```bash
# Run from the project root
python tools/run_simulation.py path/to/scenario.json
python tools/run_simulation.py path/to/scenario.json --output-dir .tmp
```

- Results are saved to `.tmp/results_{scenario_name}_{timestamp}.json`
- A summary table is printed to stdout
- Exit code 0 = success, 1 = error

---

### Option C — Programmatic (import the engine directly)

```python
import sys
sys.path.insert(0, "tools")
from monte_carlo_engine import run_simulation

config = { ... }  # see schema below
results = run_simulation(config)

print(results["statistics"]["success_probability"])
print(results["statistics"]["percentiles"])
```

---

## Expected Outputs

| Field | Description |
|---|---|
| `success_probability` | Fraction of paths meeting all success criteria |
| `mean_final` / `median_final` / `std_final` | Final portfolio value statistics |
| `min_final` / `max_final` | Extremes across all paths |
| `percentiles` | p5, p10, p25, p50, p75, p90, p95 of final values |
| `expected_shortfall_5pct` | Mean of worst 5% of final values |
| `fan_chart_data` | Percentile bands per time step (detailed mode only) |
| `sample_paths` | Up to 50 individual paths (detailed mode only) |
| `final_values` | All final portfolio values (always present; used for histogram) |
| `run_metadata` | Duration, timestamp, seed, mode |

---

## Scenario Config Schema

```json
{
  "scenario": {
    "name": "my_retirement",
    "description": "Base case, 40-year horizon",
    "type": "retirement"
  },
  "timeline": {
    "start_date": "2025-01-01",
    "end_date": "2065-01-01",
    "time_step_years": 1.0
  },
  "initial_state": {
    "portfolio_value": 500000,
    "annual_contribution": 20000,
    "annual_withdrawal": 0
  },
  "uncertainty": {
    "expected_return_mean": 0.07,
    "volatility_std": 0.15,
    "distribution": "lognormal_gbm",
    "correlation_matrix": null,
    "shock_events": [
      {
        "label": "market_crash",
        "annual_probability": 0.05,
        "impact_multiplier": 0.65
      }
    ]
  },
  "constraints": {
    "wealth_floor": 0.0
  },
  "success_criteria": {
    "target_portfolio_value": 0.0,
    "never_below_floor": true
  },
  "simulation_config": {
    "n_paths": 1000,
    "random_seed": 42,
    "mode": "fast",
    "record_full_paths": false
  }
}
```

**Key parameter notes:**
- `expected_return_mean` and `volatility_std` are annual decimals (e.g., 0.07 = 7%)
- `impact_multiplier` for shocks is a decimal multiplier on portfolio value (e.g., 0.65 = crash to 65%)
- `mode: "fast"` — vectorized, stores only final values; low memory
- `mode: "detailed"` — stores full path matrix; enables fan chart; set `record_full_paths: true`
- `random_seed: null` — uses system entropy (non-reproducible)

---

## Math Reference

**GBM wealth process** (per time step of size Δt):
```
Z  ~ N(0, 1)                     # standard normal draw
R  = (μ - 0.5σ²)·Δt + σ·√Δt·Z  # log-return
W' = (W + C - D) · exp(R)        # update wealth (C = contribution, D = withdrawal)
W' = max(W', floor)              # enforce floor
```

**Shock events** (applied after each return, independently):
```
For each shock event:
    if uniform(0,1) < p_shock · Δt:
        W' = W' × impact_multiplier
```

**Success criteria:**
- `never_below_floor = true`: path never touched `wealth_floor` at any step
- `target_portfolio_value > 0`: final value ≥ target
- Both conditions combined with AND when both are set

**Expected shortfall at 5%:** mean of the worst 5% of final values across all paths.

---

## Performance Guide

| Paths | Steps | Mode | Typical time |
|---|---|---|---|
| 1,000 | 40 | fast | < 0.1s |
| 10,000 | 40 | fast | < 0.5s |
| 10,000 | 40 | detailed | < 1s |
| 100,000 | 40 | fast | ~3s |

Fan chart (detailed mode) at 10,000 paths × 40 steps ≈ 3.2 MB RAM.

---

## Edge Cases and Known Constraints

- **Withdrawals > portfolio**: if annual withdrawals consistently exceed contributions + returns,
  the portfolio will hit the floor — this is correct behavior, not a bug.
- **Very long horizons + small dt**: e.g., 100 years at monthly steps = 1,200 steps.
  Memory in detailed mode = n_paths × 1200 × 8 bytes. Use fast mode for > 500 steps.
- **High shock probability**: shock events with `annual_probability > 0.5` combined with low
  `impact_multiplier` produce heavily left-skewed distributions — validate that this matches intent.
- **Reproducibility**: set `random_seed` to a fixed integer. The same seed + config always
  produces identical results (uses NumPy's PCG64 generator).
- **Floor breach tracking in fast mode**: the engine tracks whether each path ever breached the
  floor during the simulation (O(n_paths) boolean array) — accurate even in fast mode.
- **Correlation matrix**: currently accepted in schema but not yet used in the single-asset GBM
  engine. Reserved for multi-asset extension.

---

## Files

| File | Role |
|---|---|
| `tools/monte_carlo_engine.py` | Pure simulation engine — all math lives here |
| `tools/run_simulation.py` | CLI runner — loads JSON, calls engine, saves results |
| `tools/api_server.py` | FastAPI server — HTTP interface + serves static UI |
| `static/index.html` | Browser UI shell |
| `static/app.js` | Frontend logic, Chart.js charts, scenario save/load |
| `requirements.txt` | Python dependencies |
| `.tmp/` | Output landing zone for CLI results |

---

## Updating This Workflow

Update this document when:
- New distribution types are added to the engine (e.g., triangular via scipy)
- Multi-asset support (Cholesky correlation) is implemented
- New simulation verticals are added (savings goal, project risk)
- Performance thresholds or recommended path counts change
- New output fields are added to the results schema
- The API schema changes (add version header if breaking)
