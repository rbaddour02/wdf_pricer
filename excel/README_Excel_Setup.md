# Excel Setup Instructions for OTC Curve Pricer

This guide explains how to set up Excel to work with the OTC Curve Pricer system using CSV handoff (no VBA).

## Overview

The workflow is:
1. **Edit inputs in Excel** → Save as `data/inputs.csv`
2. **Run Python pricer** → Generates `data/outputs.csv`
3. **Refresh Excel Outputs sheet** → Power Query imports `data/outputs.csv`

## Step 1: Create Inputs Sheet

1. Open a new Excel workbook
2. Create a sheet named **"Inputs"**
3. Create a table with the following columns (in this exact order):
   - `section` - Values: "meta", "param", "base", "anchor"
   - `key` - Identifier for the row (e.g., "curve_family", "base_ws", "anchor_ws")
   - `month` - Tenor code (e.g., "A01", "A02", ...) - **blank for meta/param rows**
   - `value` - Numeric value or string (for meta)
   - `time` - DateTime string for anchors (format: "YYYY-MM-DD HH:MM:SS") - **blank otherwise**
   - `active` - 1 for active anchors, 0 for inactive - **blank otherwise**

4. **Minimum required rows:**
   ```
   section,key,month,value,time,active
   meta,curve_family,,wdf,,
   meta,asof_date,,2026-02-08,,
   base,base_ws,A01,182,,
   base,base_ws,A02,180,,
   ... (all tenors you want to price)
   anchor,anchor_ws,A03,195,2026-02-08 09:41:00,1
   ```

5. Format as an Excel Table (Ctrl+T) for easier editing

## Step 2: Create Outputs Sheet with Power Query

1. Create a new sheet named **"Outputs"**
2. Go to **Data** → **Get Data** → **From File** → **From Text/CSV**
3. Navigate to `data/outputs.csv` in your project folder
4. In the preview dialog:
   - Click **Transform Data** (not Load)
   - Verify columns: month, base, broker, implied, dev, band, score, flag, effective_weight
   - Click **Close & Load** → **Close & Load To...**
   - Select **Table** and choose **Existing worksheet** → select cell A1 in Outputs sheet
   - Click **OK**

5. **Add Refresh Button:**
   - Right-click on the query result table
   - Select **Refresh** (or press Alt+F5)
   - Optionally: Add a button from **Developer** tab → **Insert** → **Button (Form Control)**
   - Assign macro: Right-click table → **Refresh** (or use Data → Refresh All)

## Step 3: Workflow

### Daily Usage:

1. **Edit Inputs:**
   - Open Excel workbook
   - Edit values in the Inputs table (change base values, add/modify anchors, etc.)
   - Save workbook normally (Ctrl+S)

2. **Export to CSV:**
   - Select the Inputs table
   - **File** → **Save As**
   - Choose location: `data/inputs.csv`
   - File type: **CSV (Comma delimited) (*.csv)**
   - Click **Save**
   - Excel will warn about losing formatting - click **Yes**

3. **Run Python Pricer:**
   ```bash
   python src/run_pricer.py
   ```
   Or use the Jupyter notebook: `notebooks/01_excel_io_demo.ipynb`

4. **Refresh Outputs in Excel:**
   - Go to Outputs sheet
   - Right-click the table → **Refresh**
   - Or press **Alt+F5**
   - Or use **Data** → **Refresh All**

## Step 4: Optional - Format Outputs Sheet

1. **Format the table:**
   - Apply conditional formatting to `flag` column:
     - OK → Green fill
     - YELLOW → Yellow fill
     - RED → Red fill
     - N/A → Gray fill

2. **Add formulas (optional):**
   - Add summary statistics row below table
   - Count flags: `=COUNTIF(Table1[flag],"RED")`
   - Average score: `=AVERAGE(Table1[score])`

## Troubleshooting

### Power Query not refreshing:
- Check that `data/outputs.csv` exists and is not open in another program
- Verify file path in Power Query: **Data** → **Queries & Connections** → Right-click query → **Properties** → Check path

### CSV format issues:
- Ensure inputs.csv uses comma delimiter (not semicolon)
- Check that datetime strings are in format: "YYYY-MM-DD HH:MM:SS"
- Verify no extra commas in text fields

### Missing columns:
- If outputs.csv structure changes, update Power Query:
  - **Data** → **Queries & Connections** → Right-click query → **Edit**
  - Adjust column selection if needed
  - **Close & Load**

## Example Inputs Table Structure

| section | key | month | value | time | active |
|---------|-----|-------|-------|------|--------|
| meta | curve_family | | wdf | | |
| meta | asof_date | | 2026-02-08 | | |
| param | cov_window_days | | 252 | | |
| param | shrink_lambda | | 0.1 | | |
| param | z | | 1.5 | | |
| param | sigma_min | | 0.5 | | |
| param | sigma_max | | 5.0 | | |
| param | half_life_min | | 120 | | |
| base | base_ws | A01 | 182 | | |
| base | base_ws | A02 | 180 | | |
| base | base_ws | A03 | 178 | | |
| ... | ... | ... | ... | ... | ... |
| anchor | anchor_ws | A03 | 195 | 2026-02-08 09:41:00 | 1 |
| anchor | anchor_ws | A02 | 190 | 2026-02-08 07:55:00 | 1 |

## Notes

- **No VBA required** - Everything uses standard Excel features
- **Power Query** handles CSV import automatically
- **Manual Save As CSV** is required (Excel doesn't auto-export tables to CSV)
- Keep Excel workbook and Python project in sync by refreshing after each Python run
