"""Estimate historical return covariance matrices."""

import os
import pickle
import re
import numpy as np
import pandas as pd
from typing import Tuple, Optional, List
from pathlib import Path

try:
    from sklearn.covariance import LedoitWolf
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from .parsing import extract_curve_families
from .utils import sort_tenors, check_matrix_conditioning


def load_historical_data(csv_path: str, curve_family: str) -> Tuple[pd.DataFrame, List[str]]:
    """
    Load historical data for a specific curve family.
    
    Args:
        csv_path: Path to data_.csv
        curve_family: Curve family name (e.g., 'wdf')
        
    Returns:
        Tuple of (dataframe with date index, sorted list of tenors)
    """
    df = pd.read_csv(csv_path)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    
    # Extract columns for this curve family
    pattern = f'^{re.escape(curve_family)}_A\\d{{2}}$'
    tenor_cols = [col for col in df.columns if re.match(pattern, col)]
    
    if not tenor_cols:
        raise ValueError(f"No columns found for curve family '{curve_family}'")
    
    # Extract tenors and sort
    tenors = sort_tenors([col.split('_')[-1] for col in tenor_cols])
    selected_cols = [f"{curve_family}_{tenor}" for tenor in tenors]
    
    # Select and sort by date
    curve_df = df[selected_cols].copy()
    curve_df = curve_df.sort_index()
    
    # Rename columns to just tenor codes
    curve_df.columns = tenors
    
    return curve_df, tenors


def compute_daily_returns(curve_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute daily returns (changes): R_t = X_t - X_{t-1}.
    
    Args:
        curve_df: DataFrame with date index and tenor columns
        
    Returns:
        DataFrame of daily returns
    """
    returns = curve_df.diff().dropna()
    return returns


def estimate_covariance(returns: pd.DataFrame, shrink_lambda: float = 0.1) -> np.ndarray:
    """
    Estimate covariance matrix with shrinkage.
    
    Prefers Ledoit-Wolf if available, otherwise manual shrinkage.
    
    Args:
        returns: DataFrame of daily returns (T x N)
        shrink_lambda: Shrinkage parameter for manual method
        
    Returns:
        Covariance matrix (N x N)
    """
    returns_array = returns.values
    
    if HAS_SKLEARN and len(returns) > 10:
        # Use Ledoit-Wolf shrinkage
        lw = LedoitWolf()
        lw.fit(returns_array)
        cov = lw.covariance_
    else:
        # Manual shrinkage: Σ_shrunk = (1-λ)Σ + λ*diag(Σ)
        sample_cov = np.cov(returns_array.T)
        diag_cov = np.diag(np.diag(sample_cov))
        cov = (1 - shrink_lambda) * sample_cov + shrink_lambda * diag_cov
    
    return cov


def get_covariance(
    csv_path: str,
    curve_family: str,
    window_days: int = 252,
    shrink_lambda: float = 0.1,
    cache_dir: Optional[str] = None,
    use_cache: bool = False,
) -> Tuple[np.ndarray, List[str]]:
    """
    Load or compute covariance matrix for a curve family.
    
    When use_cache=True, caches results to avoid recomputation.
    When use_cache=False (default), always recomputes from data_.csv.
    
    Args:
        csv_path: Path to data_.csv
        curve_family: Curve family name
        window_days: Number of days to use for covariance estimation
        shrink_lambda: Shrinkage parameter
        cache_dir: Directory for caching (default: data/cache/)
        use_cache: If True, load from cache when available; if False, always recompute.
        
    Returns:
        Tuple of (covariance matrix, sorted list of tenors)
    """
    if cache_dir is None:
        cache_dir = Path(csv_path).parent / "cache"
    else:
        cache_dir = Path(cache_dir)
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    cache_file = cache_dir / f"cov_{curve_family}_{window_days}.pkl"
    
    # Try to load from cache (only when use_cache is True)
    if use_cache and cache_file.exists():
        try:
            with open(cache_file, 'rb') as f:
                cached_data = pickle.load(f)
                # Verify it matches our parameters
                if (cached_data.get('window_days') == window_days and
                    cached_data.get('shrink_lambda') == shrink_lambda):
                    print(f"Loaded cached covariance for {curve_family} (window={window_days})")
                    return cached_data['cov'], cached_data['tenors']
        except Exception as e:
            print(f"Warning: Could not load cache: {e}")
    
    # Compute covariance
    print(f"Computing covariance for {curve_family} (window={window_days} days)...")
    
    curve_df, tenors = load_historical_data(csv_path, curve_family)
    returns = compute_daily_returns(curve_df)
    
    # Use last N days
    if len(returns) > window_days:
        returns = returns.tail(window_days)
    
    if len(returns) < 10:
        raise ValueError(f"Insufficient data: only {len(returns)} return observations")
    
    cov = estimate_covariance(returns, shrink_lambda)
    
    # Validate covariance matrix
    if not check_matrix_conditioning(cov, f"{curve_family} covariance"):
        print("Warning: Covariance matrix may be ill-conditioned")
    
    # Check positive semi-definite
    eigenvals = np.linalg.eigvals(cov)
    if np.any(eigenvals < -1e-8):
        print(f"Warning: Covariance has negative eigenvalues (min: {np.min(eigenvals):.2e})")
        # Make it PSD by clipping
        eigenvals = np.maximum(eigenvals, 1e-8)
        # Reconstruct (simplified - would need eigendecomposition for exact)
        cov = cov + np.eye(len(cov)) * 1e-8
    
    # Cache result
    try:
        with open(cache_file, 'wb') as f:
            pickle.dump({
                'cov': cov,
                'tenors': tenors,
                'window_days': window_days,
                'shrink_lambda': shrink_lambda
            }, f)
        print(f"Cached covariance to {cache_file}")
    except Exception as e:
        print(f"Warning: Could not cache result: {e}")
    
    return cov, tenors
