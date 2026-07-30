"""
gdp_pipeline.py
===============

Loading and cleaning for the World Bank GDP data used by the in-class demo.

Everything in this module is *ordinary data engineering work*: reading CSV files,
filtering rows, imputing missing values. None of it is specific to Apache Iceberg.

It lives here, rather than in the notebook, for the same reason it would live in a
module in a real pipeline: the notebook is the orchestration layer, and it should
read as a sequence of Iceberg operations rather than a sequence of pandas calls.

Students who want to see how the cleaning works should read this file. Students
who want to learn Iceberg can ignore it.

The Iceberg-facing utilities (show_warehouse, find_snapshot, infer_iceberg_schema
and friends) live in iceberg_helpers.py and are re-exported here, so a single
import line from this module gets you everything the demo notebook needs.

Functions defined here
----------------------
load_gdp_csv(path)          Read a World Bank GDP extract into a DataFrame.
clean_gdp(df, impute=...)   Filter and impute. Returns a new DataFrame.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Re-export the shared, dataset-agnostic helpers so the notebook needs one import.
from iceberg_helpers import (  # noqa: F401
    compare_schemas,
    find_snapshot,
    iceberg_type_for,
    infer_iceberg_schema,
    reset_tutorial,
    show_warehouse,
)

__all__ = [
    "load_gdp_csv",
    "clean_gdp",
    # re-exported from iceberg_helpers
    "infer_iceberg_schema",
    "iceberg_type_for",
    "compare_schemas",
    "show_warehouse",
    "find_snapshot",
    "reset_tutorial",
]


# ---------------------------------------------------------------------------
# 1. Loading
# ---------------------------------------------------------------------------

def load_gdp_csv(path: str) -> pd.DataFrame:
    """Read a World Bank GDP extract into a pandas DataFrame.

    The file is returned exactly as received, with no transformation applied.
    The tutorial stores this unmodified version as the *raw* Iceberg table so
    that the original input always remains recoverable.
    """
    df = pd.read_csv(path)
    print(f"Loaded {path}")
    print(f"  {len(df):,} rows x {len(df.columns)} columns")
    print(f"  columns: {list(df.columns)}")
    if "date" in df.columns:
        print(f"  year range: {df['date'].min()}-{df['date'].max()}")
    return df


# ---------------------------------------------------------------------------
# 2. Cleaning and imputation
# ---------------------------------------------------------------------------

def _impute_linear_one_country(years: pd.Series, values: pd.Series) -> pd.Series:
    """Fill missing GDP values for a single country using a linear trend in time.

    Interior gaps are interpolated between the neighbouring known years. Leading
    and trailing gaps are extrapolated from a straight line fitted to all known
    observations, using the actual year as the x axis.
    """
    values = values.astype(float)
    years = years.astype(float)
    known = values.notna()

    # Nothing to work with, or nothing missing.
    if known.sum() < 2 or known.all():
        return values

    # Interior gaps: straight-line interpolation between neighbouring known years.
    filled = values.interpolate(method="linear", limit_area="inside")

    # Leading and trailing gaps: extend the fitted trend line outward.
    slope, intercept = np.polyfit(years[known], values[known], 1)
    trend = slope * years + intercept
    return filled.where(filled.notna(), trend)


def clean_gdp(df: pd.DataFrame, impute: str | None = "ffill") -> pd.DataFrame:
    """Filter and impute a raw World Bank GDP extract.

    Steps
    -----
    1. Drop aggregate rows that have no ``countryiso3code``. These are regions
       and income groups ("Euro area", "World", "Low income"), not countries.
    2. Drop countries that have no GDP observation in any year at all.
    3. Impute the remaining missing values using the chosen strategy.
    4. Reset the index.

    Parameters
    ----------
    df : DataFrame
        The raw extract, as returned by ``load_gdp_csv``.
    impute : {"ffill", "linear", None}
        ``"ffill"``  - forward fill, then backward fill, within each country.
        ``"linear"`` - interpolate interior gaps and extrapolate the ends along
                       a fitted trend line. Negative results are clipped to zero,
                       since a negative GDP is not meaningful.
        ``None``     - apply steps 1, 2 and 4 only, leaving missing values in place.

    Returns
    -------
    DataFrame
        A new DataFrame. The input is never modified.

    Notes
    -----
    The choice of imputation strategy is a genuine analytical judgement call, not
    a detail. Two analysts can reasonably disagree. That is exactly why the
    tutorial writes both versions to the same Iceberg table: each becomes a
    separate snapshot, and the history records which choice produced which state.
    """
    if impute not in ("ffill", "linear", None):
        raise ValueError(f"impute must be 'ffill', 'linear' or None, got {impute!r}")

    n_start = len(df)

    # Step 1 - drop aggregate rows (regions and income groups, not countries).
    out = df[df["countryiso3code"].notna()].copy()
    n_aggregates = n_start - len(out)

    # Step 2 - drop countries that never have any GDP value.
    has_any_value = out.groupby("country")["value"].transform("count") > 0
    n_empty_countries = out.loc[~has_any_value, "country"].nunique()
    out = out[has_any_value].copy()

    # Step 3 - impute whatever gaps remain.
    n_missing_before = int(out["value"].isna().sum())

    if impute == "ffill":
        out = out.sort_values(["country", "date"])
        out["value"] = out.groupby("country")["value"].ffill()
        out["value"] = out.groupby("country")["value"].bfill()

    elif impute == "linear":
        out = out.sort_values(["country", "date"])
        # An explicit loop rather than groupby().apply(): the return shape of
        # apply() varies across pandas versions, and this is easier to read.
        filled = out["value"].astype(float).copy()
        for _country, group in out.groupby("country", sort=False):
            filled.loc[group.index] = _impute_linear_one_country(
                group["date"], group["value"]
            )
        # Extrapolation can run a trend line below zero; GDP cannot be negative.
        out["value"] = filled.clip(lower=0)

    n_missing_after = int(out["value"].isna().sum())

    # Step 4 - tidy up.
    out = out.sort_values(["country", "date"]).reset_index(drop=True)

    print(f"clean_gdp(impute={impute!r})")
    print(f"  dropped {n_aggregates:,} aggregate rows (no country code)")
    print(f"  dropped {n_empty_countries} countries with no data in any year")
    print(f"  missing GDP values: {n_missing_before:,} -> {n_missing_after:,}")
    print(f"  result: {len(out):,} rows x {len(out.columns)} columns")
    return out


