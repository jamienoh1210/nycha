"""
NYCHA Energy Data Processor
Reusable functions for loading, cleaning, aggregating, and merging NYCHA energy consumption data.
"""

import pandas as pd
import geopandas as gpd


def load_combined_gdf(combined_csv_path):
    """
    Load the combined NYCHA+PLUTO CSV and rebuild it as a GeoDataFrame.

    Parameters
    ----------
    combined_csv_path : str
        Path to the combined_nychares_pluto.csv file.

    Returns
    -------
    combined_gdf : GeoDataFrame
    """
    combined_df = pd.read_csv(combined_csv_path)
    combined_gdf = gpd.GeoDataFrame(
        combined_df,
        geometry=gpd.GeoSeries.from_wkt(combined_df['geometry']),
        crs='EPSG:2263'
    )
    return combined_gdf


def process_energy_csv(
    csv_path,
    consumption_col,
    combined_gdf,
    drop_columns=None,
):
    """
    Load an energy consumption CSV, clean it, aggregate by TDS #,
    and merge with the combined NYCHA+PLUTO GeoDataFrame.

    Parameters
    ----------
    csv_path : str
        Path to the raw energy CSV file.
    consumption_col : str
        Raw column name for consumption (e.g. 'Consumption (KWH)',
        'Consumption (Therms)', 'Consumption (Mlbs)').
    combined_gdf : GeoDataFrame
        The pre-loaded combined NYCHA+PLUTO GeoDataFrame.
    drop_columns : list of str, optional
        Extra columns to drop beyond the default set. If None, uses the
        default list.

    Returns
    -------
    final_gdf : GeoDataFrame
        Merged GeoDataFrame with aggregated consumption and charges.
    cleaned_df : DataFrame
        The fully cleaned (pre-aggregation) DataFrame, available for
        date-filtered analysis (e.g. 2024-only cost plots).
    """
    if drop_columns is None:
        drop_columns = [
            'edp', 'account_name', 'location', 'meter_amr',
            'meter_scope', 'umis_bill_id', 'amp_#', 'rc_code',
            'estimated', 'rate_class', 'bill_analyzed'
        ]

    # -- 1. Load raw CSV --
    df = pd.read_csv(csv_path)

    # -- 2. Clean column names --
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    # -- 3. Drop unnecessary columns --
    existing_drop_cols = [c for c in drop_columns if c in df.columns]
    df.drop(columns=existing_drop_cols, inplace=True)

    # -- 4. Normalize the consumption column name --
    raw_col_clean = consumption_col.strip().lower().replace(" ", "_")
    # Map known raw names to a standard cleaned name
    consumption_map = {
        'consumption_(kwh)': 'consumption_(kwh)',
        'consumption_(therms)': 'consumption_(therms)',
        'consumption_(mlbs)': 'consumption_(mlbs)',
    }
    clean_consumption_col = consumption_map.get(raw_col_clean, raw_col_clean)

    # -- 5. Clean consumption column: strip commas, convert to float --
    df[clean_consumption_col] = (
        df[clean_consumption_col]
        .astype(str)
        .str.replace(',', '')
        .astype(float)
    )

    # -- 6. Drop rows missing tds_# --
    df = df.dropna(subset=['tds_#'])

    # -- 7. Clean tds_#: float → int → str --
    df['tds_#'] = (
        df['tds_#']
        .astype(float)
        .astype(int)
        .astype(str)
    )

    # -- 8. Clean current_charges: strip $ and commas --
    df['current_charges'] = (
        df['current_charges']
        .astype(str)
        .str.replace('[$,]', '', regex=True)
        .str.strip()
    )
    df['current_charges'] = pd.to_numeric(df['current_charges'], errors='coerce')

    # -- 9. Further clean tds_# (remove trailing .0) --
    df['tds_#'] = (
        df['tds_#']
        .astype(str)
        .str.replace(',', '')
        .str.strip()
        .str.replace(r'\.0$', '', regex=True)
    )

    # -- 10. Aggregate by tds_# --
    consumption_agg = (
        df
        .groupby('tds_#')
        .agg({
            clean_consumption_col: 'sum',
            'current_charges': 'sum',
            'borough': 'first'
        })
        .reset_index()
    )

    # -- 11. Merge with combined GeoDataFrame --
    combined_gdf['tds_#'] = combined_gdf['tds_#'].astype(str).str.strip()
    consumption_agg['tds_#'] = consumption_agg['tds_#'].astype(str).str.strip()

    final_gdf = combined_gdf.merge(consumption_agg, on='tds_#', how='left')

    return final_gdf, df
