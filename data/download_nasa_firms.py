"""
NASA FIRMS API Connector & Regional Benchmark Downloader
Provides automated fetching from NASA EOSDIS FIRMS API:
https://firms.modaps.eosdis.nasa.gov/api/
"""

import os
import requests
import pandas as pd
from typing import Optional
from datetime import datetime, timedelta


def fetch_firms_live(
    map_key: str,
    source: str = "VIIRS_SNPP_NRT",
    area_bbox: str = "world",
    day_range: int = 1,
    date_str: Optional[str] = None
) -> pd.DataFrame:
    """
    Downloads active fire data directly from NASA FIRMS API.
    :param map_key: User's NASA FIRMS Map Key (free from https://firms.modaps.eosdis.nasa.gov/api/map_key/)
    :param source: 'MODIS_NRT', 'VIIRS_SNPP_NRT', or 'VIIRS_NOAA20_NRT'
    :param area_bbox: 'world' or 'min_lon,min_lat,max_lon,max_lat'
    :param day_range: 1 to 10 days
    """
    if date_str is None:
        date_str = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source}/{area_bbox}/{day_range}/{date_str}"
    
    print(f"Requesting NASA FIRMS: {source} for {area_bbox}...")
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"NASA FIRMS API Error {response.status_code}: {response.text}")

    from io import StringIO
    df = pd.read_csv(StringIO(response.text))
    return df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download active fires from NASA FIRMS API")
    parser.add_argument("--key", type=str, required=True, help="NASA FIRMS Map Key")
    parser.add_argument("--source", type=str, default="VIIRS_SNPP_NRT", help="MODIS_NRT or VIIRS_SNPP_NRT")
    parser.add_argument("--output", type=str, default="firms_download.csv", help="Output CSV path")
    args = parser.parse_args()

    try:
        df = fetch_firms_live(map_key=args.key, source=args.source)
        df.to_csv(args.output, index=False)
        print(f"Saved {len(df)} records to {args.output}")
    except Exception as e:
        print(f"Error: {e}")
