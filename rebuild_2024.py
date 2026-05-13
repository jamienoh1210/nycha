"""
Rebuild all energy CSVs with 2024-only data.
Run from the nycha/ directory.
"""
import pandas as pd
import geopandas as gpd
from pathlib import Path
import sys

# Add colab_cleaning to path to import energy_processor
sys.path.insert(0, str(Path(__file__).resolve().parent / "notebooks"))
from energy_processor import load_combined_gdf

base = Path(__file__).resolve().parent

# Load the combined NYCHA+PLUTO base
combined_gdf = load_combined_gdf(base / "data/processed/combined_nychares_pluto.csv")

# ============================================================
# Helper: process a raw energy CSV, filtering to 2024 only
# ============================================================
def process_2024_only(csv_path, consumption_col, combined_gdf, drop_columns=None):
    """Same as energy_processor.process_energy_csv but filters to 2024 only."""
    if drop_columns is None:
        drop_columns = [
            'edp', 'account_name', 'location', 'meter_amr',
            'meter_scope', 'umis_bill_id', 'amp_#', 'rc_code',
            'estimated', 'rate_class', 'bill_analyzed'
        ]

    df = pd.read_csv(csv_path)

    # Clean column names
    df.columns = (
        df.columns.str.strip().str.lower().str.replace(" ", "_")
    )

    # --- FILTER TO 2024 ONLY ---
    if 'revenue_month' in df.columns:
        df = df[df['revenue_month'].astype(str).str.startswith('2024')]
        print(f"  Filtered to 2024: {len(df)} rows remain")

    # Drop unnecessary columns
    existing_drop_cols = [c for c in drop_columns if c in df.columns]
    df.drop(columns=existing_drop_cols, inplace=True)

    # Normalize consumption column name
    raw_col_clean = consumption_col.strip().lower().replace(" ", "_")
    consumption_map = {
        'consumption_(kwh)': 'consumption_(kwh)',
        'consumption_(therms)': 'consumption_(therms)',
        'consumption_(mlbs)': 'consumption_(mlbs)',
    }
    clean_consumption_col = consumption_map.get(raw_col_clean, raw_col_clean)

    # Clean consumption column
    df[clean_consumption_col] = (
        df[clean_consumption_col].astype(str).str.replace(',', '').astype(float)
    )

    # Drop rows missing tds_#
    df = df.dropna(subset=['tds_#'])

    # Clean tds_#
    df['tds_#'] = df['tds_#'].astype(float).astype(int).astype(str)

    # Clean current_charges
    df['current_charges'] = (
        df['current_charges'].astype(str)
        .str.replace('[$,]', '', regex=True).str.strip()
    )
    df['current_charges'] = pd.to_numeric(df['current_charges'], errors='coerce')

    # Further clean tds_#
    df['tds_#'] = (
        df['tds_#'].astype(str).str.replace(',', '').str.strip()
        .str.replace(r'\.0$', '', regex=True)
    )

    # Aggregate by tds_#
    consumption_agg = (
        df.groupby('tds_#').agg({
            clean_consumption_col: 'sum',
            'current_charges': 'sum',
            'borough': 'first'
        }).reset_index()
    )

    # Merge with combined GeoDataFrame
    combined_gdf_copy = combined_gdf.copy()
    combined_gdf_copy['tds_#'] = combined_gdf_copy['tds_#'].astype(str).str.strip()
    consumption_agg['tds_#'] = consumption_agg['tds_#'].astype(str).str.strip()

    final_gdf = combined_gdf_copy.merge(consumption_agg, on='tds_#', how='left')

    return final_gdf, df


# ============================================================
# Process each utility for 2024 only
# ============================================================

print("=" * 60)
print("Processing STEAM (2024 only)")
print("=" * 60)
steam_gdf, _ = process_2024_only(
    base / "data/raw/Steam_Consumption_And_Cost_(2010_–_Sep_2025)_20260314.csv",
    'Consumption (Mlbs)',
    combined_gdf,
)
steam_gdf.to_csv(base / "data/processed/combined_steam_2024.csv", index=False)
print(f"  Saved {len(steam_gdf)} rows to combined_steam_2024.csv")

print("\n" + "=" * 60)
print("Processing ELECTRICITY (2024 only)")
print("=" * 60)
elec_gdf, _ = process_2024_only(
    base / "data/raw/Electric_Consumption_And_Cost_(2010_-_Sep_2025)_20260314.csv",
    'Consumption (KWH)',
    combined_gdf,
)
elec_gdf.to_csv(base / "data/processed/combined_electricity_2024.csv", index=False)
print(f"  Saved {len(elec_gdf)} rows to combined_electricity_2024.csv")

print("\n" + "=" * 60)
print("Processing HEATING GAS (2024 only)")
print("=" * 60)
gas_gdf, _ = process_2024_only(
    base / "data/raw/Heating_Gas_Consumption_And_Cost_(2010_-__Sep_2025)_20260314.csv",
    'Consumption (Therms)',
    combined_gdf,
)
gas_gdf.to_csv(base / "data/processed/combined_heating_gas_2024.csv", index=False)
print(f"  Saved {len(gas_gdf)} rows to combined_heating_gas_2024.csv")

# ============================================================
# Build combined_utilities_2024.csv
# ============================================================
print("\n" + "=" * 60)
print("Building combined_utilities_2024.csv")
print("=" * 60)

# Load the three CSVs
steamdf = pd.read_csv(base / "data/processed/combined_steam_2024.csv")
elecdf = pd.read_csv(base / "data/processed/combined_electricity_2024.csv")
gasdf = pd.read_csv(base / "data/processed/combined_heating_gas_2024.csv")

# Calculate per-unit consumption (clean unitsres first)
for gdf in [steamdf, elecdf, gasdf]:
    gdf['unitsres'] = pd.to_numeric(gdf['unitsres'].astype(str).str.replace(',', ''), errors='coerce')
    gdf['unitstotal'] = pd.to_numeric(gdf['unitstotal'].astype(str).str.replace(',', ''), errors='coerce')

steamdf['steam_consumption_per_unit'] = steamdf['consumption_(mlbs)'] / steamdf['unitsres']
elecdf['electricity_consumption_per_unit'] = elecdf['consumption_(kwh)'] / elecdf['unitsres']
gasdf['gas_consumption_per_unit'] = gasdf['consumption_(therms)'] / gasdf['unitsres']

# Rename charge columns
steamdf = steamdf.rename(columns={'current_charges': 'steam_current_charges'})
elecdf = elecdf.rename(columns={'current_charges': 'electricity_current_charges'})
gasdf = gasdf.rename(columns={'current_charges': 'gas_current_charges'})

# Keep only needed columns
keep_cols = ['BBL', 'development', 'tds_#', 'borough', 'latitude_nycha',
             'longitude_nycha', 'unitsres', 'unitstotal']

steamdf = steamdf[keep_cols + ['steam_current_charges', 'steam_consumption_per_unit']]
elecdf = elecdf[['BBL'] + ['electricity_current_charges', 'electricity_consumption_per_unit']]
gasdf = gasdf[['BBL'] + ['gas_current_charges', 'gas_consumption_per_unit']]

# Aggregate by BBL (take first for everything except charges/consumption which are already TDS-level)
steam_agg = steamdf.groupby('BBL', as_index=False).agg({
    **{col: 'first' for col in keep_cols if col != 'BBL'},
    'steam_current_charges': 'first',
    'steam_consumption_per_unit': 'first'
})

elec_agg = elecdf.groupby('BBL', as_index=False).agg({
    'electricity_current_charges': 'first',
    'electricity_consumption_per_unit': 'first'
})

gas_agg = gasdf.groupby('BBL', as_index=False).agg({
    'gas_current_charges': 'first',
    'gas_consumption_per_unit': 'first'
})

# Merge all three
combined = steam_agg.merge(elec_agg, on='BBL', how='outer')
combined = combined.merge(gas_agg, on='BBL', how='outer')

# Fix borough from BBL
borough_map = {'1': 'Manhattan', '2': 'Bronx', '3': 'Brooklyn', '4': 'Queens', '5': 'Staten Island'}
combined['borough'] = combined['BBL'].astype(str).str[0].map(borough_map)

# Convert to MMBtu (these are already per-unit, so no need to divide by units again)
combined['steam_mmbtu_per_unit'] = pd.to_numeric(combined['steam_consumption_per_unit'], errors='coerce')           # 1 Mlb = 1 MMBtu
combined['gas_mmbtu_per_unit'] = pd.to_numeric(combined['gas_consumption_per_unit'], errors='coerce') / 10          # 10 Therms = 1 MMBtu
combined['electricity_mmbtu_per_unit'] = pd.to_numeric(combined['electricity_consumption_per_unit'], errors='coerce') / 293  # 293 kWh = 1 MMBtu

combined['total_energy_mmbtu_per_unit'] = (
    combined['steam_mmbtu_per_unit'].fillna(0) +
    combined['gas_mmbtu_per_unit'].fillna(0) +
    combined['electricity_mmbtu_per_unit'].fillna(0)
)

# Total charges
combined['total_current_charges'] = (
    combined['steam_current_charges'].fillna(0) +
    combined['electricity_current_charges'].fillna(0) +
    combined['gas_current_charges'].fillna(0)
)

# Total charges per unit
units = pd.to_numeric(combined['unitsres'].astype(str).str.replace(',', ''), errors='coerce')
units = units.fillna(pd.to_numeric(combined['unitstotal'].astype(str).str.replace(',', ''), errors='coerce'))
combined['total_current_charges_per_unit'] = combined['total_current_charges'] / units

# Save
combined.to_csv(base / "data/processed/combined_utilities_2024.csv", index=False)
print(f"  Saved {len(combined)} rows to combined_utilities_2024.csv")

# Quick sanity check
print("\n" + "=" * 60)
print("SANITY CHECK - Fulton")
print("=" * 60)
fulton = combined[combined['development'] == 'FULTON']
if len(fulton) > 0:
    print(f"BBLs: {fulton['BBL'].tolist()}")
    print(f"Steam charges: {fulton['steam_current_charges'].iloc[0]:,.2f}")
    print(f"Elec charges: {fulton['electricity_current_charges'].iloc[0]:,.2f}")
    print(f"Gas charges: {fulton['gas_current_charges'].iloc[0]:,.2f}")
    print(f"Steam MMBtu/unit: {fulton['steam_mmbtu_per_unit'].iloc[0]:,.0f}")
    print(f"Total energy MMBtu/unit: {fulton['total_energy_mmbtu_per_unit'].iloc[0]:,.0f}")

print("\nDone!")