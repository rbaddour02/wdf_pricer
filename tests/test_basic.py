"""Lightweight test suite for OTC curve pricer."""

import sys
from pathlib import Path
import numpy as np

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from otc_pricer.utils import sort_tenors
from otc_pricer.parsing import parse_inputs_csv
from otc_pricer.covariance import get_covariance
from otc_pricer.inference import (
    compute_posterior,
    compute_implied_curve,
    compute_confidence_bands
)
from otc_pricer.broker import load_broker_marks


def test_tenor_sorting():
    """Test tenor parsing and ordering."""
    print("Test 1: Tenor sorting...")
    tenors = ['A15', 'A02', 'A01', 'A10', 'A03']
    sorted_tenors = sort_tenors(tenors)
    expected = ['A01', 'A02', 'A03', 'A10', 'A15']
    assert sorted_tenors == expected, f"Expected {expected}, got {sorted_tenors}"
    print("  ✓ Passed")


def test_no_anchors_implies_base():
    """Test that with no anchors, implied == base."""
    print("Test 2: No anchors → implied == base...")
    
    # Create minimal inputs
    data_dir = project_root / "data"
    historical_path = data_dir / "data_.csv"
    cache_dir = data_dir / "cache"
    
    # Use WDF curve family
    curve_family = "wdf"
    cov, tenors = get_covariance(
        str(historical_path),
        curve_family,
        window_days=252,
        shrink_lambda=0.1,
        cache_dir=str(cache_dir)
    )
    
    # Create base curve
    base_curve = {tenor: 180.0 for tenor in tenors[:5]}  # Use first 5 tenors
    
    # No anchors
    anchors = []
    
    # Run inference
    shock_vector, posterior_cov = compute_posterior(
        cov[:5, :5],  # Use subset of covariance
        anchors,
        base_curve,
        tenors[:5],
        sigma_min=0.5,
        sigma_max=5.0,
        half_life_min=120
    )
    
    # Compute implied
    implied_curve = compute_implied_curve(base_curve, shock_vector, tenors[:5])
    
    # Check that implied == base (within numerical tolerance)
    for tenor in tenors[:5]:
        base_val = base_curve[tenor]
        implied_val = implied_curve[tenor]
        assert abs(implied_val - base_val) < 1e-6, \
            f"Tenor {tenor}: base={base_val}, implied={implied_val}"
    
    print("  ✓ Passed")


def test_single_fresh_anchor():
    """Test that single fresh anchor makes implied at anchor tenor ≈ anchor price."""
    print("Test 3: Single fresh anchor → implied ≈ anchor price...")
    
    data_dir = project_root / "data"
    historical_path = data_dir / "data_.csv"
    cache_dir = data_dir / "cache"
    
    curve_family = "wdf"
    cov, tenors = get_covariance(
        str(historical_path),
        curve_family,
        window_days=252,
        shrink_lambda=0.1,
        cache_dir=str(cache_dir)
    )
    
    # Create base curve
    base_curve = {tenor: 180.0 for tenor in tenors[:5]}
    
    # Single fresh anchor at A03
    anchor_tenor = 'A03'
    anchor_price = 195.0
    anchors = [{
        'month': anchor_tenor,
        'value': anchor_price,
        'age_minutes': 5  # Very fresh
    }]
    
    # Run inference
    shock_vector, posterior_cov = compute_posterior(
        cov[:5, :5],
        anchors,
        base_curve,
        tenors[:5],
        sigma_min=0.5,
        sigma_max=5.0,
        half_life_min=120
    )
    
    # Compute implied
    implied_curve = compute_implied_curve(base_curve, shock_vector, tenors[:5])
    
    # Check that implied at anchor tenor is close to anchor price
    implied_at_anchor = implied_curve[anchor_tenor]
    tolerance = 2.0  # Allow some tolerance due to covariance structure
    assert abs(implied_at_anchor - anchor_price) < tolerance, \
        f"Anchor {anchor_tenor}: expected ≈{anchor_price}, got {implied_at_anchor}"
    
    print(f"  ✓ Passed (implied={implied_at_anchor:.2f}, anchor={anchor_price:.2f}, diff={abs(implied_at_anchor - anchor_price):.2f})")


def test_recency_effect():
    """Test that fresh anchor has smaller band than stale anchor."""
    print("Test 4: Recency effect (fresh < stale band)...")
    
    data_dir = project_root / "data"
    historical_path = data_dir / "data_.csv"
    cache_dir = data_dir / "cache"
    
    curve_family = "wdf"
    cov, tenors = get_covariance(
        str(historical_path),
        curve_family,
        window_days=252,
        shrink_lambda=0.1,
        cache_dir=str(cache_dir)
    )
    
    base_curve = {tenor: 180.0 for tenor in tenors[:5]}
    anchor_tenor = 'A03'
    anchor_price = 195.0
    z = 1.5
    
    # Fresh anchor (5 minutes)
    anchors_fresh = [{
        'month': anchor_tenor,
        'value': anchor_price,
        'age_minutes': 5
    }]
    
    shock_fresh, cov_post_fresh = compute_posterior(
        cov[:5, :5],
        anchors_fresh,
        base_curve,
        tenors[:5],
        sigma_min=0.5,
        sigma_max=5.0,
        half_life_min=120
    )
    bands_fresh = compute_confidence_bands(cov_post_fresh, z)
    
    # Stale anchor (480 minutes = 8 hours)
    anchors_stale = [{
        'month': anchor_tenor,
        'value': anchor_price,
        'age_minutes': 480
    }]
    
    shock_stale, cov_post_stale = compute_posterior(
        cov[:5, :5],
        anchors_stale,
        base_curve,
        tenors[:5],
        sigma_min=0.5,
        sigma_max=5.0,
        half_life_min=120
    )
    bands_stale = compute_confidence_bands(cov_post_stale, z)
    
    # Average band should be smaller for fresh anchor
    avg_band_fresh = np.mean(bands_fresh)
    avg_band_stale = np.mean(bands_stale)
    
    assert avg_band_fresh < avg_band_stale, \
        f"Fresh anchor band ({avg_band_fresh:.4f}) should be < stale ({avg_band_stale:.4f})"
    
    print(f"  ✓ Passed (fresh avg={avg_band_fresh:.4f}, stale avg={avg_band_stale:.4f})")


def run_all_tests():
    """Run all tests."""
    print("="*60)
    print("Running OTC Curve Pricer Tests")
    print("="*60)
    print()
    
    try:
        test_tenor_sorting()
        test_no_anchors_implies_base()
        test_single_fresh_anchor()
        test_recency_effect()
        
        print()
        print("="*60)
        print("All tests passed! ✓")
        print("="*60)
        return 0
    except AssertionError as e:
        print()
        print("="*60)
        print(f"Test failed: {e}")
        print("="*60)
        return 1
    except Exception as e:
        print()
        print("="*60)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
