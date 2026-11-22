"""Build the bundled SEC snapshot when the Streamlit data stores are missing."""

from contextlib import closing
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

import duckdb
from filelock import FileLock, Timeout

from .filing_index import open_index
from .filings import ANALYTICS, INDEX, ROOT, WAREHOUSE, original_filings
from .sec import SecError
from .sources import CUTOFF

LOG = logging.getLogger(__name__)
STORE_NAMES = (WAREHOUSE.name, ANALYTICS.name, INDEX.name)


class BootstrapError(RuntimeError):
    """A startup step could not prepare the local data stores."""


def _validate_stores(directory: Path, *, frozen: bool = False):
    warehouse, analytics, index = (directory / name for name in STORE_NAMES)
    for store in (warehouse, analytics, index):
        if not store.is_file() or store.stat().st_size == 0:
            raise ValueError(f"Missing or empty store: {store.name}")

    expected = {(f.ticker, f.fiscal_year, f.accession) for f in original_filings(warehouse)}
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        source_snapshot = connection.execute("SELECT as_of_date FROM snapshot").fetchall()
        if connection.execute("SELECT count(*) FROM raw_xbrl_facts").fetchone()[0] == 0:
            raise ValueError("The SEC warehouse contains no XBRL facts.")
    with duckdb.connect(str(analytics), read_only=True) as connection:
        analytics_snapshot = connection.execute("SELECT as_of_date FROM analysis_snapshot").fetchall()
        periods = connection.execute(
            "SELECT ticker, fiscal_year, original_accession FROM annual_financial_analytics"
        ).fetchall()
        if connection.execute("SELECT count(*) FROM statement_lineage").fetchone()[0] == 0:
            raise ValueError("Financial analytics contains no statement lineage.")
    if (len(source_snapshot) != 1 or source_snapshot != analytics_snapshot
            or (frozen and source_snapshot != [(CUTOFF,)])):
        raise ValueError("The source and analytics snapshot dates do not match the requested data.")
    if len(periods) != len(expected) or set(periods) != expected:
        raise ValueError("Analytics periods do not match the original SEC filings.")

    with closing(open_index(index)) as connection:
        filings = connection.execute("SELECT ticker, fiscal_year, accession FROM filings").fetchall()
        indexed = {row[0] for row in connection.execute("SELECT DISTINCT accession FROM passages")}
    if {tuple(row) for row in filings} != expected or indexed != {row[2] for row in expected}:
        raise ValueError("The filing index does not cover the original SEC filings.")


def _run(root: Path, stage: str, module: str, *args):
    LOG.info("EquityLens startup: %s", stage)
    try:
        subprocess.run(
            [sys.executable, "-m", module, *map(str, args)],
            cwd=root, check=True, timeout=300,
            env={**os.environ, "MPLBACKEND": "Agg", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
        )
    except subprocess.CalledProcessError as exc:
        raise BootstrapError(f"{stage} exited with code {exc.returncode}. See the app logs.") from exc
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError(f"{stage} exceeded five minutes. See the app logs.") from exc


def _build(root: Path, staging: Path):
    snapshots = root / "data/snapshots"
    source_cache = staging / "sec-json"
    filing_cache = staging / "sec-10ks"
    for suffix, cache in (("sec-json", source_cache), ("sec-10k-html", filing_cache)):
        with ZipFile(snapshots / f"{CUTOFF}-{suffix}.zip") as archive:
            archive.extractall(cache)

    warehouse, analytics, index = (staging / name for name in STORE_NAMES)
    _run(root, "Build and verify SEC warehouse", "src.equitylens", "--offline",
         "--cache", source_cache, "--database", warehouse, "--reports", staging / "reports",
         "--verify-manifest", snapshots / f"{CUTOFF}-source-manifest.json")
    _run(root, "Build and verify financial analytics", "src.equitylens.analytics",
         "--source", warehouse, "--database", analytics, "--reports", staging / "reports/analytics")
    _run(root, "Build and verify searchable filing index", "src.equitylens.research",
         "--warehouse", warehouse, "--index", index, "index", "--offline", "--cache", filing_cache,
         "--manifest", staging / "filings.json",
         "--verify-manifest", snapshots / f"{CUTOFF}-10k-manifest.json")


def ensure_data(root: Path = ROOT):
    """Reuse a valid set of stores, or stage and publish a checked offline rebuild."""
    directory = root / "data/warehouse"
    publishing = directory / ".bootstrap-publishing"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with FileLock(directory / ".bootstrap.lock", timeout=960):
            if not publishing.exists() and all((directory / name).is_file() for name in STORE_NAMES):
                try:
                    _validate_stores(directory)
                    return
                except (OSError, ValueError, duckdb.Error, sqlite3.Error, SecError) as exc:
                    LOG.warning("Existing EquityLens stores did not validate: %s. Rebuilding.", exc)

            with TemporaryDirectory(prefix=".bootstrap-", dir=directory) as temporary:
                staging = Path(temporary)
                _build(root, staging)
                _validate_stores(staging, frozen=True)
                # An interrupted publication must be retried even if all filenames exist.
                publishing.touch()
                for name in STORE_NAMES:
                    (staging / name).replace(directory / name)
                publishing.unlink()
            LOG.info("EquityLens offline snapshot is ready.")
    except Timeout as exc:
        raise BootstrapError("Timed out waiting for another process to initialize the data stores.") from exc
    except (OSError, ValueError, BadZipFile, duckdb.Error, sqlite3.Error, SecError) as exc:
        raise BootstrapError(f"Could not prepare the bundled SEC snapshot: {exc}") from exc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        ensure_data()
    except BootstrapError as exc:
        LOG.error("%s", exc)
        raise SystemExit(1) from exc
