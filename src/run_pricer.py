"""Main entry point for OTC curve pricer."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
HISTORICAL_PATH = DATA_DIR / "data_.csv"
INPUTS_PATH = DATA_DIR / "inputs.csv"
OUTPUTS_PATH = DATA_DIR / "outputs.csv"
CACHE_DIR = DATA_DIR / "cache"

from otc_pricer.parsing import parse_inputs_csv, compute_anchor_ages
from otc_pricer.covariance import get_covariance
from otc_pricer.inference import (
    compute_posterior,
    compute_implied_curve,
    compute_confidence_bands,
    compute_effective_weights
)
from otc_pricer.broker import (
    load_broker_marks,
    compute_staleness_metrics
)
from otc_pricer.io_csv import write_outputs_csv


def main():
    """Run the OTC curve pricer pipeline."""
    if not INPUTS_PATH.exists():
        print(f"Error: {INPUTS_PATH} not found")
        return 1
    
    if not HISTORICAL_PATH.exists():
        print(f"Error: {HISTORICAL_PATH} not found")
        return 1
    
    # Load inputs
    print("Loading inputs...")
    inputs = parse_inputs_csv(INPUTS_PATH)
    
    meta = inputs['meta']
    params = inputs['params']
    base_curve = inputs['base']
    anchors = inputs['anchors']
    
    curve_family = meta.get('curve_family')
    asof_date = meta.get('asof_date')
    
    if not curve_family:
        print("Error: curve_family not specified in inputs.csv")
        return 1
    
    if not asof_date:
        print("Error: asof_date not specified in inputs.csv")
        return 1
    
    # Extract parameters with defaults
    cov_window_days = params.get('cov_window_days', 252)
    shrink_lambda = params.get('shrink_lambda', 0.1)
    z = params.get('z', 1.5)
    sigma_min = params.get('sigma_min', 0.5)
    sigma_max = params.get('sigma_max', 5.0)
    half_life_min = params.get('half_life_min', 120)
    
    # Load/compute covariance
    print(f"Loading covariance for {curve_family}...")
    try:
        cov, tenors = get_covariance(
            str(HISTORICAL_PATH),
            curve_family,
            window_days=cov_window_days,
            shrink_lambda=shrink_lambda,
            cache_dir=str(CACHE_DIR)
        )
    except Exception as e:
        print(f"Error computing covariance: {e}")
        return 1
    
    # Ensure base curve has all tenors (fill missing with 0)
    for tenor in tenors:
        if tenor not in base_curve:
            base_curve[tenor] = 0.0
    
    # Compute anchor ages
    asof_time = meta.get('asof_time')
    anchors_with_ages = compute_anchor_ages(anchors, asof_date, asof_time)
    
    # Run Bayesian inference
    print("Running Bayesian inference...")
    try:
        shock_vector, posterior_cov = compute_posterior(
            cov,
            anchors_with_ages,
            base_curve,
            tenors,
            sigma_min,
            sigma_max,
            half_life_min
        )
    except Exception as e:
        print(f"Error in inference: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Compute implied curve
    implied_curve = compute_implied_curve(base_curve, shock_vector, tenors)
    
    # Compute confidence bands
    bands = compute_confidence_bands(posterior_cov, z)
    
    # Compute effective weights
    weights = compute_effective_weights(posterior_cov)
    
    # Load broker marks
    print("Loading broker marks...")
    broker_marks = load_broker_marks(
        str(HISTORICAL_PATH),
        curve_family,
        asof_date,
        tenors
    )
    
    # Compute staleness metrics
    staleness = compute_staleness_metrics(
        broker_marks,
        implied_curve,
        bands,
        tenors
    )
    
    # Write outputs
    print("Writing outputs...")
    write_outputs_csv(
        str(OUTPUTS_PATH),
        tenors,
        base_curve,
        broker_marks,
        implied_curve,
        bands,
        weights,
        staleness
    )
    
    # Print summary
    num_anchors = len([a for a in anchors_with_ages if a.get('month') in tenors])
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Curve family:     {curve_family}")
    print(f"As-of date:       {asof_date}")
    print(f"Active anchors:   {num_anchors}")
    print(f"Covariance window: {cov_window_days} days")
    print(f"Tenors:           {len(tenors)}")
    print("="*60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
