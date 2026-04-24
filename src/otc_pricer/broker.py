"""Broker marks extraction and staleness metrics computation."""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional

from .utils import sort_tenors


def load_broker_marks(
    csv_path: str,
    curve_family: str,
    asof_date: str,
    tenors: List[str]
) -> Dict[str, Optional[float]]:
    """
    Load broker marks from data_.csv on asof_date with forward-fill.
    
    Args:
        csv_path: Path to data_.csv
        curve_family: Curve family name
        asof_date: Date string (YYYY-MM-DD)
        tenors: List of tenors to extract
        
    Returns:
        Dict mapping tenor -> broker mark (or None if unavailable)
    """
    df = pd.read_csv(csv_path)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    df = df.sort_index()
    
    asof_dt = pd.to_datetime(asof_date)
    
    # Extract columns for this curve family
    broker_marks = {}
    missing_tenors = []
    
    for tenor in tenors:
        col_name = f"{curve_family}_{tenor}"
        
        if col_name not in df.columns:
            broker_marks[tenor] = None
            missing_tenors.append(tenor)
            continue
        
        # Try to get value on asof_date
        if asof_dt in df.index:
            val = df.loc[asof_dt, col_name]
            if pd.notna(val):
                broker_marks[tenor] = float(val)
                continue
        
        # Forward-fill from most recent prior date
        prior_data = df.loc[df.index <= asof_dt, col_name]
        prior_data = prior_data.dropna()
        
        if len(prior_data) > 0:
            broker_marks[tenor] = float(prior_data.iloc[-1])
        else:
            broker_marks[tenor] = None
            missing_tenors.append(tenor)
    
    if missing_tenors:
        print(f"Warning: Broker marks missing for {len(missing_tenors)} tenors: {missing_tenors[:5]}{'...' if len(missing_tenors) > 5 else ''}")
    
    return broker_marks


def compute_staleness_metrics(
    broker_marks: Dict[str, Optional[float]],
    implied_curve: Dict[str, float],
    confidence_bands: np.ndarray,
    tenors: List[str],
    yellow_threshold: float = 1.2,
    red_threshold: float = 2.0
) -> Dict[str, Dict]:
    """
    Compute staleness metrics for each tenor.
    
    dev = broker - implied
    score = abs(dev) / band
    flag: OK (<yellow_threshold), YELLOW (yellow_threshold-red_threshold), RED (≥red_threshold)
    
    Args:
        broker_marks: Dict mapping tenor -> broker mark
        implied_curve: Dict mapping tenor -> implied value
        confidence_bands: Array of band widths
        tenors: Sorted list of tenors
        yellow_threshold: Score threshold for YELLOW flag (default 1.2)
        red_threshold: Score threshold for RED flag (default 2.0)
        
    Returns:
        Dict mapping tenor -> {dev, score, flag}
    """
    metrics = {}
    
    for i, tenor in enumerate(tenors):
        broker = broker_marks.get(tenor)
        implied = implied_curve.get(tenor, 0.0)
        band = confidence_bands[i]
        
        if broker is not None:
            dev = broker - implied
            score = abs(dev) / band if band > 0 else float('inf')
            
            if score < yellow_threshold:
                flag = "OK"
            elif score < red_threshold:
                flag = "YELLOW"
            else:
                flag = "RED"
        else:
            dev = None
            score = None
            flag = "N/A"
        
        metrics[tenor] = {
            'dev': dev,
            'score': score,
            'flag': flag
        }
    
    return metrics
