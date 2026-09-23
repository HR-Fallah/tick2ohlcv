from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

ZIP_RE = re.compile(r"HISTDATA_COM_ASCII_(?P<symbol>[A-Z]+)_T(?P<period>\d{6})\.zip$", re.IGNORECASE)
CSV_RE = re.compile(r"DAT_ASCII_(?P<symbol>[A-Z]+)_T_(?P<period>\d{6})\.csv$", re.IGNORECASE)


@dataclass(frozen=True)
class SourceFile:
    symbol: str
    period: str # "YYYYMM"
    path: Path
    csv_name: str | None

    @property
    def is_zip(self) -> bool:
        return self.csv_name is not None


def discover(data_dir: Path) -> dict[str, list[SourceFile]]:
    """Scan `data_dir` recursively and return {symbol: [SourceFile, ...]},
    each list sorted chronologically."""
    found: dict[str, dict[str, SourceFile]] = {}

    for path in data_dir.rglob("*"):
        if not path.is_file():
            continue

        m = ZIP_RE.match(path.name)
        if m:
            symbol, period = m.group("symbol").upper(), m.group("period")
            csv_name = _csv_name_inside(path, symbol, period)
            found.setdefault(symbol, {})[period] = SourceFile(symbol, period, path, csv_name)
            continue

        m = CSV_RE.match(path.name)
        if m:
            symbol, period = m.group("symbol").upper(), m.group("period")
            found.setdefault(symbol, {})
            found[symbol].setdefault(period, SourceFile(symbol, period, path, None))  # zip wins if both exist

    return {symbol: [periods[p] for p in sorted(periods)] for symbol, periods in sorted(found.items())}


def _csv_name_inside(zip_path: Path, symbol: str, period: str) -> str:
    expected = f"DAT_ASCII_{symbol}_T_{period}.csv"
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if expected in names:
            return expected
        csv_candidates = [n for n in names if n.lower().endswith(".csv")]
        if csv_candidates:
            return csv_candidates[0]
    raise FileNotFoundError(f"No .csv member found inside {zip_path}")


def filter_symbols(all_files: dict[str, list[SourceFile]], symbols: list[str] | None) -> dict[str, list[SourceFile]]:
    if not symbols or symbols == ["all"]:
        return all_files
    wanted = {s.upper() for s in symbols}
    missing = wanted - all_files.keys()
    if missing:
        raise ValueError(f"Requested symbol(s) not found in data dir: {sorted(missing)}. "
                          f"Available: {sorted(all_files.keys())}")
    return {s: all_files[s] for s in wanted}


def filter_periods(files: list[SourceFile], start: str | None, end: str | None) -> list[SourceFile]:
    if start:
        files = [f for f in files if f.period >= start]
    if end:
        files = [f for f in files if f.period <= end]
    return files
