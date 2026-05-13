"""
NYCHA Energy Data Processor
Reusable functions for loading, cleaning, aggregating, and merging NYCHA energy consumption data.
"""

import pandas as pd
import geopandas as gpd


def load_combined_gdf(combined_csv_path):
    """
  
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
   
    if drop_columns is None:
        drop_columns = [
            'edp', 'account_name', 'location', 'meter_amr',
            'meter_scope', 'umis_bill_id', 'amp_#', 'rc_code',
            'estimated', 'rate_class', 'bill_analyzed'
        ]

    # First we load raw CSV
    df = pd.read_csv(csv_path)

    # We clean column names
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    # We drop unnecessary columns
    existing_drop_cols = [c for c in drop_columns if c in df.columns]
    df.drop(columns=existing_drop_cols, inplace=True)

    # We standardize the consumption column name
    raw_col_clean = consumption_col.strip().lower().replace(" ", "_")
    # We map known raw names to a standard cleaned name
    consumption_map = {
        'consumption_(kwh)': 'consumption_(kwh)',
        'consumption_(therms)': 'consumption_(therms)',
        'consumption_(mlbs)': 'consumption_(mlbs)',
    }
    clean_consumption_col = consumption_map.get(raw_col_clean, raw_col_clean)

    # We clean consumption column
    df[clean_consumption_col] = (
        df[clean_consumption_col]
        .astype(str)
        .str.replace(',', '')
        .astype(float)
    )

    # We drop rows missing tds_#
    df = df.dropna(subset=['tds_#'])

    # We clean tds_#
    df['tds_#'] = (
        df['tds_#']
        .astype(float)
        .astype(int)
        .astype(str)
    )

    # We clean current_charges
    df['current_charges'] = (
        df['current_charges']
        .astype(str)
        .str.replace('[$,]', '', regex=True)
        .str.strip()
    )
    df['current_charges'] = pd.to_numeric(df['current_charges'], errors='coerce')

    # We remove trailing .0 from TDS
    df['tds_#'] = (
        df['tds_#']
        .astype(str)
        .str.replace(',', '')
        .str.strip()
        .str.replace(r'\.0$', '', regex=True)
    )

    # We aggregate by tds_#
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

    # We merge with combined GeoDataFrame
    combined_gdf['tds_#'] = combined_gdf['tds_#'].astype(str).str.strip()
    consumption_agg['tds_#'] = consumption_agg['tds_#'].astype(str).str.strip()

    final_gdf = combined_gdf.merge(consumption_agg, on='tds_#', how='left')

    return final_gdf, df
