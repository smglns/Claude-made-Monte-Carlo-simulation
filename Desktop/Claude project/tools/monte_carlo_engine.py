"""
Monte Carlo simulation engine — pure computation, no I/O, no side effects.

Input:  scenario config dict (matches the JSON schema defined in the workflow SOP)
Output: results dict with statistics, fan chart data, and simulation metadata
"""

import time
import math
from datetime import datetime, date

import numpy as np


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_simulation(config: dict) -> dict:
    """
    Run a Monte Carlo simulation from a scenario config dict.

    Returns a results dict with:
      - statistics: success_probability, mean/median/std, percentiles, expected_shortfall
      - fan_chart_data: percentile bands over time (detailed mode only)
      - sample_paths: up to 50 individual paths (detailed mode only)
      - final_values: all final portfolio values (always present, for histogram)
      - run_metadata: timing, seed, mode
    """
    _validate_config(config)

    sim_cfg = config["simulation_config"]
    n_paths = sim_cfg["n_paths"]
    seed = sim_cfg.get("random_seed", None)
    mode = sim_cfg.get("mode", "fast")
    record_full = sim_cfg.get("record_full_paths", False) or (mode == "detailed")

    rng = np.random.default_rng(seed)

    time_axis = _build_time_axis(config)
    n_steps = len(time_axis) - 1
    dt = config["timeline"]["time_step_years"]

    W0 = config["initial_state"]["portfolio_value"]
    contrib = config["initial_state"].get("annual_contribution", 0.0)
    withdraw = config["initial_state"].get("annual_withdrawal", 0.0)
    net_cashflow = (contrib - withdraw) * dt  # scale cashflow to step size

    mu = config["uncertainty"]["expected_return_mean"]
    sigma = config["uncertainty"]["volatility_std"]
    floor = config["constraints"].get("wealth_floor", 0.0)
    shock_events = config["uncertainty"].get("shock_events", [])

    success_cfg = config["success_criteria"]
    target = success_cfg.get("target_portfolio_value", 0.0)
    never_below = success_cfg.get("never_below_floor", True)

    t0 = time.perf_counter()

    if record_full:
        paths_matrix, ever_breached = _simulate_paths_detailed(
            W0, net_cashflow, mu, sigma, dt, n_steps, n_paths, floor, shock_events, rng
        )
        final_values = paths_matrix[:, -1]
        fan_chart_data = _compute_fan_chart(paths_matrix)
        sample_paths = paths_matrix[:50, :].tolist()
    else:
        final_values, ever_breached = _simulate_paths_fast(
            W0, net_cashflow, mu, sigma, dt, n_steps, n_paths, floor, shock_events, rng
        )
        fan_chart_data = None
        sample_paths = None

    duration = time.perf_counter() - t0

    statistics = _compute_statistics(final_values, target, floor, never_below, ever_breached)

    return {
        "scenario_name": config["scenario"]["name"],
        "n_paths": n_paths,
        "n_steps": n_steps,
        "time_axis": time_axis.tolist(),
        "statistics": statistics,
        "fan_chart_data": fan_chart_data,
        "sample_paths": sample_paths,
        "final_values": final_values.tolist(),
        "run_metadata": {
            "duration_seconds": round(duration, 4),
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "random_seed": seed,
            "mode": mode,
        },
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_config(config: dict) -> None:
    errors = []

    # Timeline
    tl = config.get("timeline", {})
    try:
        start = date.fromisoformat(tl["start_date"])
        end = date.fromisoformat(tl["end_date"])
        if end <= start:
            errors.append("end_date must be after start_date")
    except (KeyError, ValueError) as e:
        errors.append(f"Invalid timeline dates: {e}")

    dt = tl.get("time_step_years", 1.0)
    if dt <= 0:
        errors.append("time_step_years must be positive")

    # Initial state
    state = config.get("initial_state", {})
    if state.get("portfolio_value", 0) <= 0:
        errors.append("portfolio_value must be positive")

    # Uncertainty
    unc = config.get("uncertainty", {})
    sigma = unc.get("volatility_std", 0)
    if sigma <= 0:
        errors.append("volatility_std must be positive")

    for evt in unc.get("shock_events", []):
        p = evt.get("annual_probability", 0)
        m = evt.get("impact_multiplier", 1)
        if not (0 < p < 1):
            errors.append(f"shock '{evt.get('label')}' annual_probability must be in (0, 1)")
        if not (0 < m < 1):
            errors.append(f"shock '{evt.get('label')}' impact_multiplier must be in (0, 1)")

    # Constraints
    floor = config.get("constraints", {}).get("wealth_floor", 0.0)
    if floor < 0:
        errors.append("wealth_floor must be >= 0")

    # Simulation config
    sim = config.get("simulation_config", {})
    n = sim.get("n_paths", 1000)
    if not (1 <= n <= 100_000):
        errors.append("n_paths must be between 1 and 100,000")

    if errors:
        raise ValueError("Invalid simulation config:\n" + "\n".join(f"  - {e}" for e in errors))


# ---------------------------------------------------------------------------
# Time axis
# ---------------------------------------------------------------------------

def _build_time_axis(config: dict) -> np.ndarray:
    """Return year-offset array [0, dt, 2*dt, ..., T] where T = total horizon in years."""
    tl = config["timeline"]
    start = date.fromisoformat(tl["start_date"])
    end = date.fromisoformat(tl["end_date"])
    dt = tl["time_step_years"]

    total_years = (end - start).days / 365.25
    n_steps = max(1, math.floor(total_years / dt))
    return np.linspace(0.0, n_steps * dt, n_steps + 1)


# ---------------------------------------------------------------------------
# Simulation engines
# ---------------------------------------------------------------------------

def _simulate_paths_fast(
    W0: float,
    net_cashflow: float,
    mu: float,
    sigma: float,
    dt: float,
    n_steps: int,
    n_paths: int,
    wealth_floor: float,
    shock_events: list,
    rng: np.random.Generator,
) -> tuple:
    """
    Vectorized GBM — stores only the running wealth vector (memory-efficient).

    Returns:
        (final_values: shape (n_paths,), ever_breached: shape (n_paths,) bool)
    """
    W = np.full(n_paths, float(W0))
    ever_breached = np.zeros(n_paths, dtype=bool)

    sigma_sq_half = 0.5 * sigma ** 2
    sigma_sqrt_dt = sigma * math.sqrt(dt)
    drift = (mu - sigma_sq_half) * dt

    for _ in range(n_steps):
        Z = rng.standard_normal(n_paths)
        R = drift + sigma_sqrt_dt * Z
        W = (W + net_cashflow) * np.exp(R)

        # Apply shock events independently
        for evt in shock_events:
            p_step = evt["annual_probability"] * dt
            shock_mask = rng.random(n_paths) < p_step
            W = np.where(shock_mask, W * evt["impact_multiplier"], W)

        # Enforce floor
        breached_this_step = W < wealth_floor
        ever_breached |= breached_this_step
        W = np.maximum(W, wealth_floor)

    return W, ever_breached


def _simulate_paths_detailed(
    W0: float,
    net_cashflow: float,
    mu: float,
    sigma: float,
    dt: float,
    n_steps: int,
    n_paths: int,
    wealth_floor: float,
    shock_events: list,
    rng: np.random.Generator,
) -> tuple:
    """
    Vectorized GBM — stores full path matrix.

    Returns:
        (paths_matrix: shape (n_paths, n_steps+1), ever_breached: shape (n_paths,) bool)
    """
    paths = np.empty((n_paths, n_steps + 1))
    paths[:, 0] = W0
    ever_breached = np.zeros(n_paths, dtype=bool)

    sigma_sq_half = 0.5 * sigma ** 2
    sigma_sqrt_dt = sigma * math.sqrt(dt)
    drift = (mu - sigma_sq_half) * dt

    W = np.full(n_paths, float(W0))

    for t in range(n_steps):
        Z = rng.standard_normal(n_paths)
        R = drift + sigma_sqrt_dt * Z
        W = (W + net_cashflow) * np.exp(R)

        for evt in shock_events:
            p_step = evt["annual_probability"] * dt
            shock_mask = rng.random(n_paths) < p_step
            W = np.where(shock_mask, W * evt["impact_multiplier"], W)

        breached_this_step = W < wealth_floor
        ever_breached |= breached_this_step
        W = np.maximum(W, wealth_floor)

        paths[:, t + 1] = W

    return paths, ever_breached


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _compute_statistics(
    final_values: np.ndarray,
    target: float,
    floor: float,
    never_below_floor: bool,
    ever_breached: np.ndarray,
) -> dict:
    n = len(final_values)

    # Success criteria
    if never_below_floor and target > 0:
        success_mask = (~ever_breached) & (final_values >= target)
    elif never_below_floor:
        success_mask = ~ever_breached
    elif target > 0:
        success_mask = final_values >= target
    else:
        success_mask = final_values > floor

    success_probability = float(np.sum(success_mask)) / n

    # Core statistics
    mean_final = float(np.mean(final_values))
    median_final = float(np.median(final_values))
    std_final = float(np.std(final_values))
    min_final = float(np.min(final_values))
    max_final = float(np.max(final_values))

    # Percentiles
    pcts = np.percentile(final_values, [5, 10, 25, 50, 75, 90, 95])
    percentiles = {
        "p5": float(pcts[0]),
        "p10": float(pcts[1]),
        "p25": float(pcts[2]),
        "p50": float(pcts[3]),
        "p75": float(pcts[4]),
        "p90": float(pcts[5]),
        "p95": float(pcts[6]),
    }

    # Expected shortfall at 5%
    cutoff_idx = max(1, int(math.ceil(0.05 * n)))
    worst = np.sort(final_values)[:cutoff_idx]
    expected_shortfall_5pct = float(np.mean(worst))

    return {
        "success_probability": round(success_probability, 6),
        "mean_final": mean_final,
        "median_final": median_final,
        "std_final": std_final,
        "min_final": min_final,
        "max_final": max_final,
        "percentiles": percentiles,
        "expected_shortfall_5pct": expected_shortfall_5pct,
    }


# ---------------------------------------------------------------------------
# Fan chart
# ---------------------------------------------------------------------------

def _compute_fan_chart(paths_matrix: np.ndarray) -> dict:
    """Compute percentile bands across the time axis. Input shape: (n_paths, n_steps+1)."""
    pcts = np.percentile(paths_matrix, [5, 10, 25, 50, 75, 90, 95], axis=0)
    return {
        "p5": pcts[0].tolist(),
        "p10": pcts[1].tolist(),
        "p25": pcts[2].tolist(),
        "p50": pcts[3].tolist(),
        "p75": pcts[4].tolist(),
        "p90": pcts[5].tolist(),
        "p95": pcts[6].tolist(),
    }
