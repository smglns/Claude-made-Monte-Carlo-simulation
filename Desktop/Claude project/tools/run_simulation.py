"""
CLI runner for the Monte Carlo simulation engine.

Usage:
    python tools/run_simulation.py path/to/scenario.json
    python tools/run_simulation.py path/to/scenario.json --output-dir .tmp
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow imports from the tools/ directory when run from the project root
sys.path.insert(0, str(Path(__file__).parent))
import monte_carlo_engine as engine


def main():
    parser = argparse.ArgumentParser(
        description="Run a Monte Carlo financial simulation from a JSON config file."
    )
    parser.add_argument("config_path", help="Path to the scenario config JSON file")
    parser.add_argument(
        "--output-dir",
        default=".tmp",
        help="Directory to write results JSON (default: .tmp)",
    )
    args = parser.parse_args()

    config = _load_config(args.config_path)

    print(f"\nRunning simulation: {config.get('scenario', {}).get('name', 'unnamed')}")
    print(f"  Paths: {config.get('simulation_config', {}).get('n_paths', 1000)}")
    print(f"  Mode:  {config.get('simulation_config', {}).get('mode', 'fast')}")
    print()

    try:
        results = engine.run_simulation(config)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    output_path = _save_results(results, args.output_dir)
    _print_summary(results)
    print(f"\nResults saved to: {output_path}")


def _load_config(path: str) -> dict:
    resolved = Path(path).resolve()
    if not resolved.exists():
        print(f"ERROR: Config file not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(resolved) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)


def _save_results(results: dict, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    name = results["scenario_name"].replace(" ", "_").lower()
    filename = f"results_{name}_{ts}.json"
    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    return output_path


def _print_summary(results: dict) -> None:
    stats = results["statistics"]
    meta = results["run_metadata"]
    pcts = stats["percentiles"]

    def fmt(v):
        return f"${v:>14,.0f}"

    def pct(v):
        return f"{v * 100:>6.1f}%"

    sep = "-" * 50

    print(sep)
    print(f"  Scenario : {results['scenario_name']}")
    print(f"  Paths    : {results['n_paths']:,}   Steps: {results['n_steps']}")
    print(f"  Duration : {meta['duration_seconds']:.2f}s   Seed: {meta['random_seed']}")
    print(sep)
    print(f"  Success probability : {pct(stats['success_probability'])}")
    print(sep)
    print(f"  Mean final value    : {fmt(stats['mean_final'])}")
    print(f"  Median final value  : {fmt(stats['median_final'])}")
    print(f"  Std deviation       : {fmt(stats['std_final'])}")
    print(f"  Min / Max           : {fmt(stats['min_final'])} / {fmt(stats['max_final'])}")
    print(sep)
    print("  Percentiles:")
    for label, key in [("  5th", "p5"), (" 10th", "p10"), (" 25th", "p25"),
                       (" 50th", "p50"), (" 75th", "p75"), (" 90th", "p90"), (" 95th", "p95")]:
        print(f"    {label}   {fmt(pcts[key])}")
    print(sep)
    print(f"  Expected shortfall (worst 5%) : {fmt(stats['expected_shortfall_5pct'])}")
    print(sep)


if __name__ == "__main__":
    main()
