"""Command-line interface for refreshing or rebuilding the SEC warehouse."""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
from dotenv import load_dotenv

from .report import write_reports
from .sec import SecClient, SecError
from .sources import CUTOFF, FIRST_YEAR
from .warehouse import build

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Use saved SEC JSON only")
    mode.add_argument("--refresh", action="store_true", help="Redownload all required SEC JSON")
    parser.add_argument("--as-of", type=date.fromisoformat, default=CUTOFF)
    parser.add_argument("--cache", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--database", type=Path, default=ROOT / "data/warehouse/equitylens.duckdb")
    parser.add_argument("--reports", type=Path, default=ROOT / "reports/generated")
    parser.add_argument("--verify-manifest", type=Path, help="Verify an archived offline source manifest")
    args = parser.parse_args()
    if args.verify_manifest and not args.offline:
        parser.error("--verify-manifest requires --offline")
    if args.as_of.year < FIRST_YEAR:
        parser.error(f"--as-of must be in {FIRST_YEAR} or later")
    load_dotenv(ROOT / ".env")
    client = SecClient(
        args.cache, os.getenv("SEC_ORGANIZATION", "EquityLens"), os.getenv("SEC_CONTACT_EMAIL", ""),
        offline=args.offline, refresh=args.refresh,
    )
    try:
        args.database.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=args.database.parent) as temporary:
            staged = Path(temporary) / "warehouse.duckdb"
            with duckdb.connect(str(staged)) as connection:
                build(connection, client, args.as_of)
                if args.verify_manifest:
                    expected = json.loads(args.verify_manifest.read_text(encoding="utf-8"))
                    actual = {"as_of_date": str(args.as_of),
                              "sources": sorted(client.sources, key=lambda row: row["path"])}
                    if expected != actual:
                        raise SecError("Source manifest differs from the requested snapshot.")
            staged.replace(args.database)
        with duckdb.connect(str(args.database), read_only=True) as connection:
            counts = write_reports(connection, args.reports, client.sources)
    except (SecError, OSError, ValueError, duckdb.Error) as exc:
        print(f"EquityLens: {exc}", file=sys.stderr)
        return 1
    finally:
        client.session.close()
    print(f"Validated SEC snapshot as of {args.as_of}: {args.database}")
    for name, count in counts.items():
        print(f"  {name}: {count:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
