"""
co2_pipeline.py
===============

Loading and cleaning for the OWID CO2 emissions data used by the take-home
assignment.

This is the assignment's counterpart to ``gdp_pipeline.py``. Everything here is
ordinary pandas work, deliberately kept out of the notebook so that the notebook
is about Apache Iceberg. Your graded work is the Iceberg code, not the cleaning.

The Iceberg-facing utilities live in ``iceberg_helpers.py`` and are re-exported
here, so one import line gets you everything the assignment needs.

Functions defined here
----------------------
load_co2_csv(path)          Read an OWID CO2 extract into a DataFrame.
clean_co2(df, impute=...)   Filter and impute the ``co2`` column.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Re-export the shared, dataset-agnostic helpers.
from iceberg_helpers import (  # noqa: F401
    compare_schemas,
    find_snapshot,
    iceberg_type_for,
    infer_iceberg_schema,
    reset_tutorial,
    show_warehouse,
)

__all__ = [
    "load_co2_csv",
    "clean_co2",
    # re-exported from iceberg_helpers
    "infer_iceberg_schema",
    "iceberg_type_for",
    "compare_schemas",
    "show_warehouse",
    "find_snapshot",
    "reset_tutorial",
]

# Columns that might carry a country code, depending on which OWID extract you have.
_CODE_COLUMNS = ("iso_code", "countryiso3code", "code", "iso3")


# ---------------------------------------------------------------------------
# 1. Loading
# ---------------------------------------------------------------------------

def load_co2_csv(path: str) -> pd.DataFrame:
    """Read an OWID CO2 emissions extract into a pandas DataFrame.

    The file is returned exactly as received, with no transformation applied. The
    assignment stores this unmodified version as the *raw* Iceberg table so that
    the original input always remains recoverable.
    """
    df = pd.read_csv(path)
    print(f"Loaded {path}")
    print(f"  {len(df):,} rows x {len(df.columns)} columns")
    print(f"  columns: {list(df.columns)}")
    if "year" in df.columns:
        print(f"  year range: {df['year'].min()}-{df['year'].max()}")
    if "country" in df.columns:
        print(f"  countries: {df['country'].nunique()}")
    return df


# ---------------------------------------------------------------------------
# 2. Cleaning and imputation
# ---------------------------------------------------------------------------

def _impute_linear_one_country(years: pd.Series, values: pd.Series) -> pd.Series:
    """Fill missing values for one country using a linear trend in time.

    Interior gaps are interpolated between neighbouring known years. Leading and
    trailing gaps are extrapolated from a straight line fitted to all known
    observations, using the actual year as the x axis.
    """
    values = values.astype(float)
    years = years.astype(float)
    known = values.notna()

    if known.sum() < 2 or known.all():
        return values

    filled = values.interpolate(method="linear", limit_area="inside")
    slope, intercept = np.polyfit(years[known], values[known], 1)
    trend = slope * years + intercept
    return filled.where(filled.notna(), trend)


def clean_co2(
    df: pd.DataFrame,
    impute: str | None = "ffill",
    column: str = "co2",
    drop_aggregates: bool = True,
) -> pd.DataFrame:
    """Filter and impute an OWID CO2 extract.

    Steps
    -----
    1. Optionally drop aggregate rows. OWID mixes continents, income groups and
       "World" totals in with individual countries; those rows have no ISO code,
       or an ``OWID_`` prefixed one. Aggregating over data that already contains
       aggregates double counts, so they are removed by default.
    2. Drop countries with no observation of ``column`` in any year.
    3. Impute the remaining gaps within each country using the chosen strategy.
    4. Sort by country and year, and reset the index.

    Parameters
    ----------
    df : DataFrame
        The raw extract, as returned by ``load_co2_csv``.
    impute : {"ffill", "linear", None}
        ``"ffill"``  - forward fill, then backward fill, within each country.
        ``"linear"`` - interpolate interior gaps, extrapolate the ends along a
                       fitted trend, then clip negatives to zero.
        ``None``     - filter and sort only, leaving missing values in place.
    column : str
        Which measurement column to impute. Defaults to ``"co2"``.
    drop_aggregates : bool
        Set to ``False`` if your extract contains only individual countries.

    Returns
    -------
    DataFrame
        A new DataFrame. The input is never modified.

    Notes
    -----
    Both imputation strategies are defensible and they produce different numbers.
    That disagreement is not a nuisance to be hidden; it is exactly the kind of
    analytical decision worth recording in a table's history, which is why the
    in-class demo writes both versions as separate snapshots of one table.

    A note on a common bug
    ----------------------
    Writing ``df.groupby("country")[col].ffill().bfill()`` looks right and is not.
    ``ffill()`` returns a plain Series, so the ``bfill()`` chained onto it is no
    longer grouped and will happily carry the last value of one country backwards
    into the first years of the next. The two fills must be grouped separately,
    as they are below.
    """
    if impute not in ("ffill", "linear", None):
        raise ValueError(f"impute must be 'ffill', 'linear' or None, got {impute!r}")
    for required in ("country", "year", column):
        if required not in df.columns:
            raise KeyError(f"expected a {required!r} column, found {list(df.columns)}")

    n_start = len(df)
    out = df.copy()

    # Step 1 - drop continent / income-group / World aggregate rows.
    n_aggregates = 0
    code_column = next((c for c in _CODE_COLUMNS if c in out.columns), None)
    if drop_aggregates and code_column:
        is_country = out[code_column].notna() & ~out[code_column].astype(str).str.startswith("OWID")
        n_aggregates = int((~is_country).sum())
        out = out[is_country].copy()
    elif drop_aggregates:
        print(f"  (no country-code column found among {_CODE_COLUMNS}; keeping all rows)")

    # Step 2 - drop countries with no observation at all.
    has_any = out.groupby("country")[column].transform("count") > 0
    n_empty = out.loc[~has_any, "country"].nunique()
    out = out[has_any].copy()

    # Step 3 - impute.
    n_missing_before = int(out[column].isna().sum())

    if impute == "ffill":
        out = out.sort_values(["country", "year"])
        # Two separate grouped fills. See the note in this docstring.
        out[column] = out.groupby("country")[column].ffill()
        out[column] = out.groupby("country")[column].bfill()

    elif impute == "linear":
        out = out.sort_values(["country", "year"])
        filled = out[column].astype(float).copy()
        for _country, group in out.groupby("country", sort=False):
            filled.loc[group.index] = _impute_linear_one_country(
                group["year"], group[column]
            )
        out[column] = filled.clip(lower=0)

    n_missing_after = int(out[column].isna().sum())

    # Step 4 - tidy up.
    out = out.sort_values(["country", "year"]).reset_index(drop=True)

    print(f"clean_co2(impute={impute!r}, column={column!r})")
    print(f"  input: {n_start:,} rows")
    if n_aggregates:
        print(f"  dropped {n_aggregates:,} aggregate rows (continents, income groups, World)")
    if n_empty:
        print(f"  dropped {n_empty} countries with no {column} data in any year")
    print(f"  missing {column} values: {n_missing_before:,} -> {n_missing_after:,}")
    print(f"  result: {len(out):,} rows x {len(out.columns)} columns")
    return out
