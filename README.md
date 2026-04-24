# OTC Curve Pricer

A Python-based OTC (Over-The-Counter) curve pricing system that uses historical covariance of daily changes and anchor noise with recency weighting to compute implied curves. The system is generalized to work with any curve family in the historical dataset.

## Features

- **Excel Integration (No VBA)**: CSV handoff workflow with Power Query refresh
- **Generalized Curve Support**: Works with any curve family in `data/data_.csv`
- **Bayesian Inference**: Combines historical covariance with anchor observations
- **Recency Weighting**: Fresh anchors have stronger influence than stale ones
- **Visual Inspection**: Jupyter notebook for debugging and visualization
- **Broker Comparison**: Compares implied curves against broker marks with staleness metrics

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Prepare Inputs

Edit `data/inputs.csv` with your curve family, base values, and anchors:

```csv
section,key,month,value,time,active
meta,curve_family,,wdf,,
meta,asof_date,,2026-02-08,,
base,base_ws,A01,182,,
base,base_ws,A02,180,,
...
anchor,anchor_ws,A03,195,2026-02-08 09:41:00,1
```

See `data/inputs.csv` for a complete example.

### 2. Run Pricer

```bash
python src/run_pricer.py
```

This will:
- Read `data/inputs.csv`
- Load historical data from `data/data_.csv`
- Compute/load covariance matrix (cached in `data/cache/`)
- Run Bayesian inference
- Write `data/outputs.csv`

### 3. Visual Inspection (Optional)

Open `notebooks/01_excel_io_demo.ipynb` to:
- View parsed inputs
- See outputs as dataframe
- Generate matplotlib visualizations
- Debug pricing results

## Excel Workflow

### Setup

1. **Create Inputs Sheet:**
   - Create table with columns: `section`, `key`, `month`, `value`, `time`, `active`
   - See `excel/README_Excel_Setup.md` for detailed instructions

2. **Create Outputs Sheet:**
   - Use Power Query to import `data/outputs.csv`
   - Add refresh button for easy updates

### Daily Usage

1. Edit inputs in Excel
2. **Save As** → `data/inputs.csv` (CSV format)
3. Run `python src/run_pricer.py`
4. Refresh Outputs sheet in Excel (Alt+F5)

See `excel/README_Excel_Setup.md` for complete Excel setup instructions.

## File Structure

```
otc_curve_pricer_2/
├── data/
│   ├── data_.csv              # Historical wide dataset (all curve families)
│   ├── inputs.csv             # User inputs (from Excel)
│   ├── outputs.csv            # Generated outputs (to Excel)
│   ├── cache/                 # Cached covariance matrices
│   └── inputs_htt.csv         # Example for HTT curve family
├── excel/
│   └── README_Excel_Setup.md  # Excel setup instructions
├── notebooks/
│   └── 01_excel_io_demo.ipynb # Visual inspection notebook
├── src/
│   ├── run_pricer.py          # Main entry point
│   └── otc_pricer/
│       ├── __init__.py
│       ├── parsing.py         # CSV parsing, curve family extraction
│       ├── covariance.py      # Σ estimation + caching
│       ├── inference.py       # Posterior mean/cov + bands
│       ├── broker.py          # Broker marks + staleness metrics
│       ├── io_csv.py         # CSV I/O utilities
│       └── utils.py           # Tenor sorting, date parsing, etc.
├── tests/
│   └── test_basic.py         # Lightweight test suite
├── requirements.txt
└── README.md
```

## Input CSV Specification

`data/inputs.csv` must have these columns:

- `section`: "meta" | "param" | "base" | "anchor"
- `key`: Identifier (e.g., "curve_family", "base_ws")
- `month`: Tenor code (A01..Axx) - blank for meta/params
- `value`: Numeric or string value
- `time`: DateTime string for anchors - blank otherwise
- `active`: 1/0 for anchors - blank otherwise

**Minimum required rows:**
- `meta,curve_family,,<curve_family>`
- `meta,asof_date,,YYYY-MM-DD`
- `base,base_ws,A01,<num>` ... (all tenors to price)

## Output CSV Specification

`data/outputs.csv` columns:

- `month`: Tenor code
- `base`: Base curve value
- `broker`: Broker mark (or empty if unavailable)
- `implied`: Implied curve value
- `dev`: Deviation (broker - implied)
- `band`: Confidence band width
- `score`: Staleness score (|dev| / band)
- `flag`: OK / YELLOW / RED / N/A
- `effective_weight`: Confidence proxy (1 / variance)

## Using Different Curve Families

The system automatically detects available curve families from `data/data_.csv`:

1. **List available families:**
   ```python
   from otc_pricer.parsing import extract_curve_families
   families = extract_curve_families("data/data_.csv")
   print(list(families.keys()))
   ```

2. **Update inputs.csv:**
   - Change `meta,curve_family,,wdf` to your desired family (e.g., `htt`, `clbr`, etc.)
   - Ensure base curve tenors match available tenors for that family

3. **Run pricer:**
   ```bash
   python src/run_pricer.py
   ```

See `data/inputs_htt.csv` for an example using the HTT curve family.

## Algorithm Overview

### Covariance Model

- Uses last `cov_window_days` (default 252) of daily changes
- Estimates Σ = Cov(R) where R_t = X_t - X_{t-1}
- Stabilizes with Ledoit-Wolf shrinkage (or manual shrinkage if sklearn unavailable)
- Caches per curve_family+window in `data/cache/`

### Anchor Inference

- **Prior**: s ~ N(0, Σ)
- **Observation**: y = Hs + ε, ε~N(0,R)
- **Posterior mean**: s_hat = Σ Hᵀ (H Σ Hᵀ + R + εI)⁻¹ y
- **Posterior covariance**: Σ_post = Σ - Σ Hᵀ (H Σ Hᵀ + R + εI)⁻¹ H Σ
- **Implied curve**: implied = base + s_hat

### Anchor Noise (Recency)

- σ_i² = sigma_min² + (sigma_max² - sigma_min²) * (1 - exp(-age_minutes / half_life_min))
- Defaults: sigma_min=0.5, sigma_max=5.0, half_life_min=120

### Confidence Bands

- band[j] = z * sqrt(diag(Σ_post)[j])
- Default z = 1.5

### Staleness Metrics

- dev = broker - implied
- score = |dev| / band
- flag: OK (<1.2), YELLOW (1.2-2.0), RED (≥2.0)

## Testing

Run the lightweight test suite:

```bash
python tests/test_basic.py
```

Tests cover:
- Tenor parsing and sorting
- No anchors → implied == base
- Single fresh anchor → implied ≈ anchor price
- Recency effect (fresh anchor has smaller band than stale)

## Configuration

Key parameters (set in `data/inputs.csv` under `param` section):

- `cov_window_days`: Historical window for covariance (default: 252)
- `shrink_lambda`: Shrinkage parameter (default: 0.1)
- `z`: Z-score multiplier for bands (default: 1.5)
- `sigma_min`: Minimum anchor noise std dev (default: 0.5)
- `sigma_max`: Maximum anchor noise std dev (default: 5.0)
- `half_life_min`: Half-life for anchor noise decay in minutes (default: 120)

## Troubleshooting

### "No columns found for curve family"
- Verify curve family name matches exactly (case-sensitive)
- Check `data/data_.csv` has columns matching pattern: `<family>_A##`

### "Insufficient data"
- Need at least 10 return observations for covariance estimation
- Check `cov_window_days` parameter

### Excel Power Query not refreshing
- Ensure `data/outputs.csv` exists and is not locked
- Check file path in Power Query properties

### Missing broker marks
- System will forward-fill from prior dates
- Warnings printed for missing tenors

## License

Internal use only.

## Support

For issues or questions, refer to:
- `excel/README_Excel_Setup.md` for Excel setup
- `notebooks/01_excel_io_demo.ipynb` for visual inspection
- Code docstrings for API documentation
