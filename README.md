# Apache Iceberg Open Table Format: Hands-on Tutorial

A complete, ready-to-deploy teaching module for introducing **Apache Iceberg** in
graduate business analytics, data engineering, and database courses.

Everything runs locally in Docker. No cloud account, no credentials, no cost.

This repository accompanies the paper:

> Kayhan, V. O., & Berndt, D. J. *Apache Iceberg Open Table Format: Hands-on Tutorial.*
> Communications of the Association for Information Systems. [under review / DOI to be added]

---

## What this module teaches

Data used for analysis is rarely static. New years arrive, historical values get
corrected, and providers change the structure of their files without warning. Teams
that manage this with `dataset_v2.csv` and `dataset_final_cleaned.csv` lose the ability
to reproduce their own results.

Working through a longitudinal World Bank GDP dataset that changes the way real
sources change, students learn to:

- create, update, and query Iceberg tables
- use snapshot-based versioning with custom metadata
- revert datasets to earlier states using time travel
- manage schema evolution

The module is built around Kolb's Experiential Learning Cycle and its objectives are
mapped to Bloom's Revised Taxonomy. Full rationale is in the paper.

---

## Quick start

**Prerequisite:** [Docker Desktop](https://www.docker.com/products/docker-desktop/),
installed and running.

```bash
# 1. Download this repository as a ZIP and extract it, or:
git clone <REPO-URL> iceberg_tutorial
cd iceberg_tutorial

# 2. Build and start the environment
docker compose up --build
```

The first build downloads the base images and takes several minutes. Later sessions
reuse the cached image and start in seconds — use `docker compose up` without
`--build`.

**Then open <http://127.0.0.1:8889/lab> in your browser** and go to the `notebooks`
folder.

> The terminal will print a URL on port **8888**. Use **8889** instead — the
> container's 8888 is mapped to 8889 on your machine so it does not collide with any
> Jupyter server you may already be running.

Start with `InClassDemo.ipynb`.

To stop everything: `Ctrl+C`, then `docker compose down`.

---

## What's in here

```
iceberg_tutorial/
├── docker-compose.yml          services: Jupyter Lab + Iceberg REST catalog
├── slides/                     instructor slide deck for the pre-demo discussion
├── app/                        Dockerfile and container build files
├── data/                       source CSVs, and the local Iceberg warehouse
└── notebooks/
    ├── InClassDemo.ipynb       the guided in-class demonstration
    ├── Assignment.ipynb        take-home assignment, with embedded grading rubric
    ├── iceberg_helpers.py      shared utilities for working with Iceberg tables
    ├── gdp_pipeline.py         loading and cleaning for the demo dataset
    └── co2_pipeline.py         loading and cleaning for the assignment dataset
```

`data/` is mounted into the container at `/tmp/warehouse`. It holds both the source
CSV files **and** the Iceberg warehouse the notebooks write into, so you will see
`gdp/` and `co2/` subfolders appear there as you work.

### The helper modules

The notebooks delegate all data cleaning to a module so that the notebook itself reads
as a sequence of Iceberg operations rather than a sequence of pandas calls. Read the
modules if you want to know exactly what the cleaning does; you do not need to in
order to follow the tutorial.

| Function | What it does |
|---|---|
| `load_gdp_csv(path)` / `load_co2_csv(path)` | read a source CSV and print a summary |
| `clean_gdp(df, impute=...)` / `clean_co2(df, impute=...)` | filter and impute; `"ffill"`, `"linear"`, or `None` |
| `infer_iceberg_schema(df)` | build a typed Iceberg `Schema` from a DataFrame's dtypes |
| `compare_schemas(table, df)` | return `(dropped, added)` columns and print a report |
| `show_warehouse(table)` | list the physical files backing a table |
| `find_snapshot(table, contains=...)` | look a snapshot up by its commit comment |
| `reset_tutorial(catalog)` | drop every table and namespace, and clear their files |

`show_warehouse()` is the one worth knowing about. It prints what Iceberg actually
wrote to disk, which is otherwise invisible:

```
Data files (.parquet): 2
    142733a0.parquet     25.4 KB  <-- read by the current snapshot
    b419dcfb.parquet     25.0 KB

Metadata alongside it:
    table metadata (.metadata.json) :   3
    manifest lists  (snap-*.avro)   :   2
    manifests       (*.avro)        :   2

Note: 1 data file(s) are on disk but not referenced by the current snapshot.
They are retained so that earlier snapshots remain readable.
```

---

## For instructors

### Where it fits

Best placed in the **latter half** of a data engineering or advanced business
analytics course, after students are comfortable with Python, Jupyter, and Docker. The
tutorial assumes they already understand what a data pipeline is; what it adds is the
versioning layer underneath one.

### Suggested class plan

| Segment | Time | Materials |
|---|---|---|
| Discussion of file versioning and Iceberg concepts | ~30 min | `slides/` |
| Hands-on demonstration, run cell by cell | 40–50 min | `InClassDemo.ipynb` |
| Debriefing: Iceberg vs. ad hoc file duplication | remainder | — |
| Take-home assignment | outside class | `Assignment.ipynb` |

**Assign the setup as pre-class work.** Have students install Docker and run
`docker compose up --build` before the session. Otherwise the class period gets spent
on installation instead of on versioning.

### The one thing students find hard

Not the commands — the metadata layer. Students accustomed to copying files expect
that a new version must mean a new copy of the data, and they struggle to accept that
dropping a column doesn't rewrite anything.

The notebook attacks this directly. `show_warehouse()` is called after every write, so
students can *see* that an overwrite leaves the superseded Parquet file sitting
untouched on disk, and that a schema change adds one small JSON file and rewrites
nothing. Slow down on those two cells; they are where the concept lands.

### The assignment

`Assignment.ipynb` gives students a different dataset (OWID global CO2 emissions) and a
partially completed notebook with `# TODO` markers. They write the Iceberg code
themselves; the data cleaning is supplied, so both their effort and your grading
concentrate on the concepts. A grading rubric is embedded in the notebook.

An instructor answer key is available on request — email the corresponding author. It
is deliberately not published here.

### Adapting it

The module is modular by design. Common adaptations:

- **Different dataset.** Write a `load_*` and `clean_*` pair following the pattern in
  `gdp_pipeline.py`, re-export the shared helpers, and the notebook structure carries
  over unchanged.
- **In-class lab instead of take-home.** The assignment works either way.
- **Shorter session.** The partitioning and UPSERT sections can be dropped without
  breaking anything earlier.
- **SQL instead of PyIceberg.** Swap the query engine for DuckDB or Spark; Iceberg is
  the storage layer either way.

---

## For students

Work through `InClassDemo.ipynb` from top to bottom. Two kinds of cell:

- **❄️ Iceberg Operation** — a callout above the cell tells you what it does, what
  Iceberg is doing underneath, what to watch for in the output, and which figure in the
  paper it matches. These are the ones that matter.
- ***Data preparation step*** — ordinary pandas. Skim it.

**Run the cells in order.** Later cells depend on earlier ones. If you lose your place,
uncomment and run `reset_tutorial(catalog)` near the top, then start again from the
beginning — snapshot counts only make sense on a clean run.

---

## Troubleshooting

**The first build seems to hang.** It isn't. Docker is downloading base images. Several
minutes is normal on a first run.

**Port 8889 is already in use.** Change the host side of the port mapping in
`docker-compose.yml` (e.g. `8890:8888`) and open that port instead.

**A table still exists after I deleted its folder.** Expected. The warehouse folder
holds the *files*; the catalog holds the *pointers* to them, and it lives inside the
`iceberg-rest-catalog` container, not in `data/`. Deleting files leaves the catalog
pointing at things that no longer exist. Always clean up through the catalog —
`reset_tutorial(catalog)` — rather than through the file system.

The reverse also happens: the REST catalog stores its state in memory by default, so
restarting that container forgets every table while the files remain on disk. A truly
clean slate needs both. This is worth two minutes of class time, because it *is* the
catalog / metadata / data separation the whole tutorial is about.

**The container crashes or the kernel dies.** Docker plus Jupyter plus Iceberg needs a
reasonable amount of RAM. On older machines, raise Docker Desktop's memory allocation
in Settings → Resources.

**Something else.** Open an issue, or ask an AI assistant — command-line and directory
navigation errors are exactly what those are good at, and resolving them yourself is
faster than waiting on the instructor.

---

## Data sources

- **World Bank**, GDP (current US$), indicator `NY.GDP.MKTP.CD` —
  <https://data.worldbank.org/indicator/NY.GDP.MKTP.CD>
- **Our World in Data**, Global CO2 emissions —
  <https://github.com/owid/co2-data>

The CSV files in `data/` are **frozen snapshots** taken on [DATE]. They are deliberately
not re-downloaded at runtime: both providers revise historical figures, and the tutorial
needs to produce identical results whenever it is run. The `month` column in the GDP
files was added by us to simulate schema drift; it is not part of the World Bank
extract.

Please check and comply with each provider's licence terms before redistributing the
data. Both are typically CC BY 4.0, but confirm before you rely on it.

---

## Citing this work

```bibtex
@article{kayhan2026iceberg,
  author  = {Kayhan, Varol O. and Berndt, Donald J.},
  title   = {Apache Iceberg Open Table Format: Hands-on Tutorial},
  journal = {Communications of the Association for Information Systems},
  year    = {2026},
  volume  = {},
  pages   = {},
  doi     = {}
}
```

---

## Licence

- **Code** (notebooks and helper modules): [MIT — confirm]
- **Teaching materials** (slides, assignment, rubric): [CC BY 4.0 — confirm]
- **Data**: see the providers' terms above.

---

## Contact

Varol O. Kayhan and Donald J. Berndt
School of Information Systems and Management, Muma College of Business,
University of South Florida

Questions, adaptations, and reports of classroom use are welcome — please open an issue
or get in touch.
