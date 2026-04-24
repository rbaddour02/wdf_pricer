"""CSV I/O utilities for reading inputs and writing outputs."""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from pathlib import Path


def write_outputs_csv(
    output_path: str,
    tenors: List[str],
    base_curve: Dict[str, float],
    broker_marks: Dict[str, Optional[float]],
    implied_curve: Dict[str, float],
    confidence_bands: np.ndarray,
    effective_weights: np.ndarray,
    staleness_metrics: Dict[str, Dict],
    return_df=False
):
    """
    Write outputs.csv with all results.
    
    Columns: month, base, broker, implied, dev, band, score, flag, effective_weight
    
    Args:
        output_path: Path to write outputs.csv
        tenors: Sorted list of tenors
        base_curve: Dict mapping tenor -> base value
        broker_marks: Dict mapping tenor -> broker mark
        implied_curve: Dict mapping tenor -> implied value
        confidence_bands: Array of band widths
        effective_weights: Array of effective weights
        staleness_metrics: Dict from compute_staleness_metrics
    """
    rows = []
    missing_broker_count = 0
    
    for i, tenor in enumerate(tenors):
        broker_val = broker_marks.get(tenor)
        if broker_val is None:
            missing_broker_count += 1
        
        row = {
            'month': tenor,
            'base': base_curve.get(tenor, 0.0),
            'broker': broker_val if broker_val is not None else '',
            'implied': implied_curve.get(tenor, 0.0),
            'dev': staleness_metrics[tenor]['dev'] if staleness_metrics[tenor]['dev'] is not None else '',
            'band': confidence_bands[i],
            'score': staleness_metrics[tenor]['score'] if staleness_metrics[tenor]['score'] is not None else '',
            'flag': staleness_metrics[tenor]['flag'],
            'effective_weight': effective_weights[i]
        }
        rows.append(row)
    
    if missing_broker_count > 0:
        print(f"Warning: {missing_broker_count} tenors have missing broker marks (written as empty strings)")
    
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False, float_format='%.6f')
    print(f"Wrote outputs to {output_path}")
    if return_df:
        return df
