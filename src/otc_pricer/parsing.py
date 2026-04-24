"""Parse inputs.csv and extract curve families from historical data."""

import re
import pandas as pd
from typing import Dict, List, Tuple, Optional
from collections import OrderedDict
from datetime import datetime, time as dt_time

from .utils import sort_tenors, parse_date, parse_datetime_flexible


def extract_curve_families(csv_path: str) -> Dict[str, List[str]]:
    """
    Extract curve families and their tenors from data_.csv.
    
    Uses regex pattern: ^(.*)_(A\\d{2})$
    
    Args:
        csv_path: Path to data_.csv
        
    Returns:
        Dict mapping curve_family -> sorted list of tenors
        Example: {'wdf': ['A01', 'A02', ..., 'A15']}
    """
    df = pd.read_csv(csv_path, nrows=1)  # Just read header
    
    families = {}
    pattern = re.compile(r'^(.*)_(A\d{2})$')
    
    for col in df.columns:
        if col == 'Date':
            continue
        
        match = pattern.match(col)
        if match:
            family = match.group(1)
            tenor = match.group(2)
            
            if family not in families:
                families[family] = []
            families[family].append(tenor)
    
    # Sort tenors for each family
    for family in families:
        families[family] = sort_tenors(families[family])
    
    return families


def parse_anchor_tenors(month_str: str) -> List[str]:
    """
    Parse anchor month field supporting both single tenors and strips.
    
    Examples:
        'A01' -> ['A01']
        'A02+A03+A04' -> ['A02', 'A03', 'A04']
        'A01+A02+A03+A04' -> ['A01', 'A02', 'A03', 'A04']
    
    Args:
        month_str: Tenor string from CSV (e.g., 'A01' or 'A02+A03+A04')
        
    Returns:
        List of tenor strings
    """
    if '+' in month_str:
        return [t.strip() for t in month_str.split('+')]
    else:
        return [month_str]


def parse_inputs_csv(df: pd.DataFrame()) -> Dict:
    """
    Parse inputs.csv into structured dictionaries.
    
    Expected format:
    section,key,month,value,time,active
    meta,curve_family,,wdf,,
    param,cov_window_days,,252,,
    base,base_ws,A01,182,,
    anchor,anchor_ws,A03,195,2026-02-08 09:41:00,1
    
    Args:
        csv_path: Path to inputs.csv
        
    Returns:
        Dict with keys: 'meta', 'params', 'base', 'anchors'
    """
    
    result = {
        'meta': {},
        'params': {},
        'base': OrderedDict(),
        'anchors': []
    }
    
    for _, row in df.iterrows():
        section = row['section']
        key = row['key']
        month = row['month'] if pd.notna(row['month']) else None
        value = row['value'] if pd.notna(row['value']) else None
        time_str = row['time'] if pd.notna(row['time']) else None
        active = row['active'] if pd.notna(row['active']) else None
        
        if section == 'meta':
            # For asof_time, use the time column instead of value column
            if key == 'asof_time':
                result['meta'][key] = time_str if time_str else value
            else:
                result['meta'][key] = value
            
        elif section == 'param':
            # Convert numeric params
            if key in ['cov_window_days', 'z']:
                result['params'][key] = int(float(value)) if value else None
            elif key in ['shrink_lambda', 'sigma_min', 'sigma_max', 'half_life_min']:
                result['params'][key] = float(value) if value else None
            else:
                result['params'][key] = value
                
        elif section == 'base':
            if month and value is not None:
                result['base'][month] = float(value)
                
        elif section == 'anchor':
            if active and int(active) == 1:
                anchor = {
                    'key': key,
                    'month': month,  # Keep original string (e.g., 'A02+A03+A04')
                    'tenors': parse_anchor_tenors(month),  # Add parsed list
                    'value': float(value) if value else None,
                    'time': time_str
                }
                result['anchors'].append(anchor)
    
    # Sort base curve by tenor
    sorted_base = OrderedDict()
    for tenor in sort_tenors(list(result['base'].keys())):
        sorted_base[tenor] = result['base'][tenor]
    result['base'] = sorted_base
    
    return result


def compute_anchor_ages(anchors: List[Dict], asof_date: str, asof_time: Optional[str] = None) -> List[Dict]:
    """
    Compute anchor ages in minutes from asof_date/time.
    
    Args:
        anchors: List of anchor dicts with 'time' field
        asof_date: Date string (YYYY-MM-DD or M/D/YYYY)
        asof_time: Optional time string (HH:MM:SS), defaults to end of day
        
    Returns:
        List of anchor dicts with added 'age_minutes' field
    """
    # Parse asof_date flexibly
    try:
        asof_date_dt = parse_datetime_flexible(asof_date)
        if asof_time:
            try:
                time_parts = asof_time.split(':')
                if len(time_parts) >= 2:
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])
                    second = int(time_parts[2]) if len(time_parts) > 2 else 0
                    asof_dt = datetime.combine(asof_date_dt.date(), dt_time(hour, minute, second))
                else:
                    asof_dt = datetime.combine(asof_date_dt.date(), dt_time(23, 59, 59))
            except Exception:
                asof_dt = datetime.combine(asof_date_dt.date(), dt_time(23, 59, 59))
        else:
            asof_dt = datetime.combine(asof_date_dt.date(), dt_time(23, 59, 59))
    except Exception as e:
        print(f"Warning: Could not parse asof_date '{asof_date}': {e}, using end of day")
        # Fallback: try to parse as YYYY-MM-DD
        try:
            asof_dt = datetime.strptime(f"{asof_date} 23:59:59", "%Y-%m-%d %H:%M:%S")
        except Exception:
            raise ValueError(f"Could not parse asof_date '{asof_date}'")
    
    result = []
    for anchor in anchors:
        if anchor.get('time'):
            try:
                anchor_dt = parse_datetime_flexible(anchor['time'])
                age_minutes = (asof_dt - anchor_dt).total_seconds() / 60.0
                anchor_copy = anchor.copy()
                anchor_copy['age_minutes'] = max(0, age_minutes)  # No negative ages
                result.append(anchor_copy)
            except Exception as e:
                print(f"Warning: Could not parse anchor time {anchor.get('time')}: {e}")
                anchor_copy = anchor.copy()
                anchor_copy['age_minutes'] = 1440  # Default to 1 day old
                result.append(anchor_copy)
        else:
            anchor_copy = anchor.copy()
            anchor_copy['age_minutes'] = 1440  # Default to 1 day old
            result.append(anchor_copy)
    
    return result
