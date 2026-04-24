"""Bayesian inference for OTC curve pricing."""

import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from .utils import sort_tenors


def compute_anchor_noise(
    age_minutes: float,
    sigma_min: float,
    sigma_max: float,
    half_life_min: float
) -> float:
    """
    Compute anchor noise variance based on recency.
    
    Model: σ_i² = sigma_min² + (sigma_max² - sigma_min²) * (1 - exp(-Δt / half_life_min))
    
    Recent anchors → small σ → strong constraint
    Old anchors → large σ → weak constraint
    
    Args:
        age_minutes: Age of anchor in minutes
        sigma_min: Minimum noise standard deviation
        sigma_max: Maximum noise standard deviation
        half_life_min: Half-life in minutes for exponential decay
        
    Returns:
        Noise variance (σ²)
    """
    decay = 1 - np.exp(-age_minutes / half_life_min)
    variance = sigma_min**2 + (sigma_max**2 - sigma_min**2) * decay
    return variance


def build_selection_matrix(tenors: List[str], anchors: List[Dict]) -> np.ndarray:
    """
    Build selection matrix H mapping full shock vector to observed anchors.
    
    For single tenor: H[i, j] = 1
    For strip (n tenors): H[i, j] = 1/n for each tenor in strip
    
    Args:
        tenors: Full sorted list of tenors (e.g., ['A01', 'A02', ..., 'A15'])
        anchors: List of anchor dicts with 'tenors' field
        
    Returns:
        Selection matrix H (K x N)
    """
    N = len(tenors)
    K = len(anchors)
    
    H = np.zeros((K, N))
    
    for i, anchor in enumerate(anchors):
        anchor_tenors = anchor.get('tenors', [anchor.get('month')])
        n_tenors = len(anchor_tenors)
        weight = 1.0 / n_tenors
        
        for anchor_tenor in anchor_tenors:
            if anchor_tenor in tenors:
                j = tenors.index(anchor_tenor)
                H[i, j] = weight
    
    return H


def compute_posterior(
    cov_prior: np.ndarray,
    anchors: List[Dict],
    base_curve: Dict[str, float],
    tenors: List[str],
    sigma_min: float,
    sigma_max: float,
    half_life_min: float,
    ridge_epsilon: float = 1e-8
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute Bayesian posterior distribution for shock vector.
    
    Prior: s ~ N(0, Σ)
    Observation: y = Hs + ε, ε~N(0,R)
    
    Posterior mean: s_hat = Σ Hᵀ (H Σ Hᵀ + R + εI)⁻¹ y
    Posterior covariance: Σ_post = Σ - Σ Hᵀ (H Σ Hᵀ + R + εI)⁻¹ H Σ
    
    Args:
        cov_prior: Prior covariance matrix Σ (N x N)
        anchors: List of anchor dicts with 'month', 'value', 'age_minutes'
        base_curve: Dict mapping tenor -> base value
        tenors: Sorted list of all tenors
        sigma_min: Minimum anchor noise std dev
        sigma_max: Maximum anchor noise std dev
        half_life_min: Half-life for anchor noise decay
        ridge_epsilon: Small value for numerical stability
        
    Returns:
        Tuple of (posterior_mean, posterior_cov)
    """
    N = len(tenors)
    
    # Handle no-anchor case
    # Filter anchors: keep if any tenor in the anchor's tenors list is in the full tenors list
    active_anchors = []
    for a in anchors:
        anchor_tenors = a.get('tenors', [a.get('month')])
        if any(t in tenors for t in anchor_tenors):
            active_anchors.append(a)
    
    if len(active_anchors) == 0:
        # No anchors: return prior (zero mean, original covariance)
        return np.zeros(N), cov_prior.copy()
    
    # Build observation vector y (anchor shocks)
    # For strips, compute shock from average base value
    y = []
    for anchor in active_anchors:
        anchor_tenors = anchor.get('tenors', [anchor.get('month')])
        # Compute average base value for the strip
        base_vals = [base_curve.get(t, 0.0) for t in anchor_tenors]
        base_avg = np.mean(base_vals)
        shock = anchor['value'] - base_avg
        y.append(shock)
    y = np.array(y)
    
    # Build selection matrix H (now takes full anchor dicts)
    H = build_selection_matrix(tenors, active_anchors)
    K = len(active_anchors)
    
    # Build noise matrix R (diagonal)
    R = np.zeros((K, K))
    for i, anchor in enumerate(active_anchors):
        age = anchor.get('age_minutes', 1440)  # Default 1 day if missing
        noise_var = compute_anchor_noise(age, sigma_min, sigma_max, half_life_min)
        R[i, i] = noise_var
    
    # Compute posterior mean: s_hat = Σ Hᵀ (H Σ Hᵀ + R + εI)⁻¹ y
    H_Sigma = H @ cov_prior  # (K x N)
    H_Sigma_HT = H_Sigma @ H.T  # (K x K)
    
    # Add ridge regularization
    ridge_matrix = ridge_epsilon * np.eye(K)
    inv_term = np.linalg.inv(H_Sigma_HT + R + ridge_matrix)
    
    s_hat = cov_prior @ H.T @ inv_term @ y  # (N,)
    
    # Compute posterior covariance: Σ_post = Σ - Σ Hᵀ (H Σ Hᵀ + R + εI)⁻¹ H Σ
    Sigma_post = cov_prior - H_Sigma.T @ inv_term @ H_Sigma
    
    # Ensure symmetry (numerical errors can cause asymmetry)
    Sigma_post = (Sigma_post + Sigma_post.T) / 2
    
    return s_hat, Sigma_post


def compute_implied_curve(
    base_curve: Dict[str, float],
    shock_vector: np.ndarray,
    tenors: List[str]
) -> Dict[str, float]:
    """
    Compute implied curve: implied = base + shock.
    
    Args:
        base_curve: Dict mapping tenor -> base value
        shock_vector: Posterior mean shock vector (N,)
        tenors: Sorted list of tenors
        
    Returns:
        Dict mapping tenor -> implied value
    """
    implied = {}
    for i, tenor in enumerate(tenors):
        base_val = base_curve.get(tenor, 0.0)
        implied[tenor] = base_val + shock_vector[i]
    
    return implied


def compute_confidence_bands(
    posterior_cov: np.ndarray,
    z: float = 1.5
) -> np.ndarray:
    """
    Compute confidence bands: band = z * sqrt(diag(Σ_post)).
    
    Args:
        posterior_cov: Posterior covariance matrix (N x N)
        z: Z-score multiplier (default 1.5)
        
    Returns:
        Array of band widths (N,)
    """
    variances = np.diag(posterior_cov)
    # Ensure non-negative
    variances = np.maximum(variances, 1e-10)
    bands = z * np.sqrt(variances)
    return bands


def compute_effective_weights(posterior_cov: np.ndarray) -> np.ndarray:
    """
    Compute effective weights as confidence proxy.
    
    effective_weight[j] = 1 / max(diag(Σ_post)[j], 1e-6)
    
    Args:
        posterior_cov: Posterior covariance matrix (N x N)
        
    Returns:
        Array of effective weights (N,)
    """
    variances = np.diag(posterior_cov)
    variances = np.maximum(variances, 1e-6)
    weights = 1.0 / variances
    return weights
