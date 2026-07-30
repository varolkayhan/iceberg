"""
iceberg_helpers.py
==================

Dataset-agnostic helpers shared by the in-class demo and the take-home assignment.

Nothing in this module knows anything about GDP or CO2 figures. It provides the
utilities that are useful whenever you are working with PyIceberg tables:

    infer_iceberg_schema(df)            DataFrame dtypes -> a typed Iceberg Schema
    iceberg_type_for(series)            the Iceberg type matching one column
    compare_schemas(table, df)          which columns differ between table and data
    show_warehouse(table, label=...)    the physical files backing a table
    find_snapshot(table, contains=...)  look a snapshot up by its commit comment
    reset_tutorial(catalog, namespaces) drop everything and start over

The dataset-specific loading and cleaning functions live in gdp_pipeline.py (the
demo) and co2_pipeline.py (the assignment). Both re-export everything here, so
`from co2_pipeline import show_warehouse` works and you only need one import line.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import pandas as pd

from pyiceberg.schema import Schema
from pyiceberg.types import (
    BooleanType,
    DoubleType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
)

__all__ = [
    "infer_iceberg_schema",
    "iceberg_type_for",
    "compare_schemas",
    "show_warehouse",
    "find_snapshot",
    "reset_tutorial",
]


# ---------------------------------------------------------------------------

# How pandas dtypes map onto Iceberg types. Anything unrecognised becomes a string.
_PANDAS_TO_ICEBERG = {
    "object": StringType(),
    "string": StringType(),
    "str": StringType(),
    "int64": LongType(),
    "Int64": LongType(),
    "float64": DoubleType(),
    "bool": BooleanType(),
    "boolean": BooleanType(),
    "datetime64[ns]": TimestampType(),
}


def iceberg_type_for(series: pd.Series):
    """Return the Iceberg type matching a pandas Series' dtype."""
    return _PANDAS_TO_ICEBERG.get(str(series.dtype), StringType())


def infer_iceberg_schema(df: pd.DataFrame, verbose: bool = True) -> Schema:
    """Build a PyIceberg ``Schema`` from a DataFrame's dtypes.

    Unlike a CSV file, an Iceberg table has an explicit, typed, versioned schema.
    Every column carries a stable field ID, which is what allows Iceberg to
    rename or drop a column later without rewriting any data files.
    """
    fields = []
    for i, (col_name, dtype) in enumerate(df.dtypes.items(), start=1):
        iceberg_type = _PANDAS_TO_ICEBERG.get(str(dtype), StringType())
        fields.append(
            NestedField(
                field_id=i,
                name=col_name,
                field_type=iceberg_type,
                required=False,
                doc=f"The {col_name} column",
            )
        )

    schema = Schema(*fields)
    if verbose:
        print("Inferred Iceberg schema:")
        for f in schema.fields:
            print(f"  field_id={f.field_id:<3} {f.name:<16} {f.field_type}")
    return schema


def compare_schemas(table, df: pd.DataFrame) -> tuple[set, set]:
    """Compare an Iceberg table's columns against a DataFrame's columns.

    Returns ``(dropped, added)`` where *dropped* are columns the table has but the
    new data does not, and *added* are columns the new data has but the table
    does not. Both are empty when the schemas match.
    """
    table_columns = {field.name for field in table.schema().fields}
    df_columns = set(df.columns)

    dropped = table_columns - df_columns
    added = df_columns - table_columns

    if not dropped and not added:
        print("Schema match. The new data fits the existing table.")
    else:
        print("SCHEMA MISMATCH")
        if dropped:
            print(f"  in the table but missing from the new data: {sorted(dropped)}")
        if added:
            print(f"  in the new data but missing from the table: {sorted(added)}")
    return dropped, added


# ---------------------------------------------------------------------------
# 4. Looking at what Iceberg actually wrote to disk
# ---------------------------------------------------------------------------

def _local_path(uri: str) -> str:
    """Turn a file:// URI into a plain local path. Non-file URIs pass through."""
    parsed = urlparse(uri)
    return parsed.path if parsed.scheme in ("", "file") else uri


def _classify(name: str) -> str:
    """Which kind of Iceberg artifact is this file?

    An Iceberg table directory holds four distinct kinds of file, and it is worth
    knowing which is which before counting anything:

    ``data``          ``*.parquet``            the rows themselves
    ``table-metadata`` ``*.metadata.json``     schema, partition spec, snapshot log
    ``manifest-list``  ``snap-*.avro``         one per snapshot: which manifests it uses
    ``manifest``       ``*.avro``              which data files exist, with column stats
    """
    if name.endswith(".parquet"):
        return "data"
    if name.endswith(".metadata.json"):
        return "table-metadata"
    if name.startswith("snap-") and name.endswith(".avro"):
        return "manifest-list"
    if name.endswith(".avro"):
        return "manifest"
    return "other"


def show_warehouse(table, label: str | None = None, list_data_files: bool = True) -> None:
    """Print the physical files backing an Iceberg table.

    This is the single most useful diagnostic in the tutorial. It shows what is
    otherwise invisible: how many data files exist, how many of them the *current*
    snapshot references, and how much metadata has accumulated alongside them.

    The gap between "on disk" and "read by the current snapshot" is what makes time
    travel possible. Superseded data files are never deleted, only unreferenced.

    Note that the counts are **per table**. If you are browsing the warehouse folder
    directly you are seeing every table at once, plus the source CSV files, plus
    anything left behind by an earlier run of the notebook.
    """
    location = _local_path(table.location())

    buckets: dict[str, list[str]] = {
        "data": [], "table-metadata": [], "manifest-list": [], "manifest": [], "other": []
    }
    for root, _dirs, files in os.walk(location):
        for name in files:
            buckets[_classify(name)].append(os.path.join(root, name))

    data_files = buckets["data"]

    # Which data files does the current snapshot actually read?
    try:
        current = {
            os.path.basename(_local_path(task.file.file_path))
            for task in table.scan().plan_files()
        }
    except Exception:
        current = set()

    try:
        table_name = ".".join(table.name())
    except TypeError:
        table_name = str(table.name())

    header = f"WAREHOUSE: {table_name}" + (f"  --  {label}" if label else "")
    print(header)
    print("-" * len(header))
    print(f"location: {location}")
    print()

    print(f"Data files (.parquet): {len(data_files)}")
    if list_data_files:
        for path in sorted(data_files):
            base = os.path.basename(path)
            size_kb = os.path.getsize(path) / 1024
            marker = "  <-- read by the current snapshot" if base in current else ""
            # Show the partition directory too, when the table is partitioned.
            parent = os.path.basename(os.path.dirname(path))
            shown = f"{parent}/{base}" if "=" in parent else base
            print(f"    {shown:<52} {size_kb:8.1f} KB{marker}")

    print()
    print("Metadata alongside it:")
    print(f"    table metadata (.metadata.json) : {len(buckets['table-metadata']):>3}")
    print(f"    manifest lists  (snap-*.avro)   : {len(buckets['manifest-list']):>3}")
    print(f"    manifests       (*.avro)        : {len(buckets['manifest']):>3}")
    if buckets["other"]:
        print(f"    other                           : {len(buckets['other']):>3}")

    total = sum(len(v) for v in buckets.values())
    print(f"    {'-' * 36}")
    print(f"    total files in this table's folder: {total}")
    print()
    print(f"Catalog currently points at: {os.path.basename(table.metadata_location)}")

    orphans = len(data_files) - len(current)
    if data_files and orphans > 0:
        print(
            f"\nNote: {orphans} data file(s) are on disk but not referenced by the "
            f"current snapshot.\nThey are retained so that earlier snapshots remain "
            f"readable."
        )


# ---------------------------------------------------------------------------
# 5. Finding a snapshot without relying on its position
# ---------------------------------------------------------------------------

def find_snapshot(table, contains: str):
    """Return the most recent snapshot whose ``comment`` property contains a string.

    Every write in this tutorial attaches custom properties (``job-name``,
    ``source-file``, ``comment``) to its snapshot. This function is why that is
    worth doing: it lets you retrieve a specific historical state by describing
    it, rather than by counting positions in a list.

    Indexing into ``table.snapshots()`` is fragile. Re-running a single cell adds
    a snapshot and silently shifts every index after it, which means a time
    travel query can return the wrong data without raising an error.
    """
    matches = [
        s for s in table.snapshots()
        if contains.lower() in str(s.summary.get("comment", "")).lower()
    ]
    if not matches:
        available = [s.summary.get("comment", "<no comment>") for s in table.snapshots()]
        raise LookupError(
            f"No snapshot comment contains {contains!r}. Available comments:\n  "
            + "\n  ".join(str(a) for a in available)
        )
    snapshot = matches[-1]
    print(f"Found snapshot {snapshot.snapshot_id}")
    print(f"  operation: {snapshot.summary.get('operation')}")
    print(f"  comment:   {snapshot.summary.get('comment')}")
    return snapshot


# ---------------------------------------------------------------------------
# 6. Starting over
# ---------------------------------------------------------------------------

def reset_tutorial(
    catalog,
    namespaces=("gdp.raw_data", "gdp.processed_data"),
    delete_files: bool = True,
) -> None:
    """Drop every table and namespace the tutorial creates.

    Run this if you lose your place. The notebook assumes a clean catalog: the
    expected snapshot and file counts in the markdown only hold on a fresh run.

    Parameters
    ----------
    delete_files : bool
        ``catalog.drop_table()`` removes the table from the catalog but leaves its
        Parquet and metadata files on disk. Re-running the notebook therefore
        accumulates orphaned files from every previous run, which makes the
        ``show_warehouse()`` counts confusing. With ``delete_files=True`` the
        table's own directory is removed as well, so the next run starts genuinely
        clean. Only directories belonging to the tutorial's own tables are touched.
    """
    import shutil

    for namespace in namespaces:
        try:
            identifiers = list(catalog.list_tables(namespace))
        except Exception:
            identifiers = []

        for identifier in identifiers:
            name = ".".join(identifier)
            location = None
            if delete_files:
                try:
                    location = _local_path(catalog.load_table(identifier).location())
                except Exception:
                    location = None
            try:
                catalog.drop_table(identifier)
                print(f"Dropped table {name}")
            except Exception as exc:
                print(f"Could not drop {name}: {exc}")
                continue

            # Guard: only delete a directory that clearly belongs to this table.
            if location and os.path.isdir(location) and identifier[-1] in location:
                shutil.rmtree(location, ignore_errors=True)
                print(f"    removed files at {location}")

        try:
            catalog.drop_namespace(namespace)
            print(f"Dropped namespace {namespace}")
        except Exception:
            pass

    print("\nCatalog reset. You can now run the notebook from the top.")
