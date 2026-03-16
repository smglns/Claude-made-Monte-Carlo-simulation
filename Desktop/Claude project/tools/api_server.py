"""
FastAPI server for the Monte Carlo simulation engine.

Startup:
    python tools/api_server.py
    # or
    uvicorn tools.api_server:app --reload --port 8000

Endpoints:
    GET  /health   — readiness check
    POST /simulate — run a simulation, returns full results JSON
    GET  /         — serves static/index.html (and static assets)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Resolve project root and add tools/ to path so the engine can be imported
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import monte_carlo_engine as engine

app = FastAPI(title="Monte Carlo Simulator", version="1.0.0")


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class ShockEvent(BaseModel):
    label: str = "shock"
    annual_probability: float = Field(gt=0, lt=1)
    impact_multiplier: float = Field(gt=0, lt=1)


class ScenarioDef(BaseModel):
    name: str = "unnamed"
    description: str = ""
    type: str = "retirement"


class Timeline(BaseModel):
    start_date: str = "2025-01-01"
    end_date: str = "2065-01-01"
    time_step_years: float = Field(default=1.0, gt=0)


class InitialState(BaseModel):
    portfolio_value: float = Field(gt=0)
    annual_contribution: float = 0.0
    annual_withdrawal: float = 0.0


class Uncertainty(BaseModel):
    expected_return_mean: float = 0.07
    volatility_std: float = Field(default=0.15, gt=0)
    distribution: str = "lognormal_gbm"
    correlation_matrix: Optional[List[List[float]]] = None
    shock_events: List[ShockEvent] = []


class Constraints(BaseModel):
    wealth_floor: float = 0.0


class SuccessCriteria(BaseModel):
    target_portfolio_value: float = 0.0
    never_below_floor: bool = True


class SimulationConfig(BaseModel):
    n_paths: int = Field(default=1000, ge=1, le=100_000)
    random_seed: Optional[int] = 42
    mode: str = "fast"
    record_full_paths: bool = False


class SimulateRequest(BaseModel):
    scenario: ScenarioDef = ScenarioDef()
    timeline: Timeline
    initial_state: InitialState
    uncertainty: Uncertainty = Uncertainty()
    constraints: Constraints = Constraints()
    success_criteria: SuccessCriteria = SuccessCriteria()
    simulation_config: SimulationConfig = SimulationConfig()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/simulate")
def simulate(request: SimulateRequest):
    config = request.model_dump()

    try:
        results = engine.run_simulation(config)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation error: {e}")

    return results


# ---------------------------------------------------------------------------
# Static file serving — MUST be mounted last (catches all remaining routes)
# ---------------------------------------------------------------------------

static_dir = PROJECT_ROOT / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False)
