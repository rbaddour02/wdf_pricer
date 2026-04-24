"""Utility functions for OTC curve pricer."""

import re
from typing import List
from datetime import datetime


def sort_tenors(tenors: List[str]) -> List[str]:
    """
    Sort tenor codes naturally (A01, A02, ..., A15).
    
    Args:
        tenors: List of tenor strings like ['A02', 'A01', 'A15']
        
    Returns:
        Sorted list ['A01', 'A02', ..., 'A15']
    """
    def tenor_key(tenor: str) -> int:
        match = re.match(r'A(\d+)', tenor)
        if match:
            return int(match.group(1))
        return 999
    
    return sorted(tenors, key=tenor_key)


def parse_date(date_str: str) -> str:
    """
    Parse date string, returning in YYYY-MM-DD format.
    
    Args:
        date_str: Date string in various formats
        
    Returns:
        Date string in YYYY-MM-DD format
    """
    # For now, assume dates are already in correct format
    # Could add more parsing logic if needed
    return date_str.strip()


def parse_datetime_flexible(dt_str) -> datetime:
    """
    Parse datetime string trying multiple formats.
    
    Handles:
    - '%Y-%m-%d %H:%M:%S' (2026-02-08 23:59:59)
    - '%m/%d/%Y %H:%M:%S' (2/8/2026 23:59:59)
    - '%m/%d/%Y %H:%M:%S' (02/08/2026 23:59:59)
    - '%Y-%m-%d' (2026-02-08) - assumes 00:00:00
    - '%m/%d/%Y' (2/8/2026) - assumes 00:00:00
    
    Args:
        dt_str: DateTime string in various formats
        
    Returns:
        datetime object
        
    Raises:
        ValueError: If no format matches
    """
    
    if not isinstance(dt_str, str):
        dt_str = str(dt_str)
    
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%m/%d/%Y %H:%M:%S',
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%Y-%m-%d %H:%M',
        '%m/%d/%Y %H:%M',
    ]
    
    dt_str = dt_str.strip()
    
    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"Could not parse datetime string '{dt_str}' with any known format")


def check_matrix_conditioning(matrix, name: str = "matrix") -> bool:
    """
    Check if matrix is well-conditioned for inversion.
    
    Args:
        matrix: numpy array
        name: Name for error messages
        
    Returns:
        True if well-conditioned, False otherwise
    """
    import numpy as np
    
    try:
        cond = np.linalg.cond(matrix)
        if cond > 1e12:
            print(f"Warning: {name} condition number is {cond:.2e}, may be ill-conditioned")
            return False
        return True
    except Exception as e:
        print(f"Error checking {name} conditioning: {e}")
        return False
