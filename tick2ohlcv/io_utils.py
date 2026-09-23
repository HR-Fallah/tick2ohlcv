from __future__ import annotations

import io
import zipfile
from collections.abc import Generator
from contextlib import contextmanager

import pandas as pd

from .discovery import SourceFile

COLUMN_NAMES = ["datetime_raw", "bid", "ask", "volume"]
DATETIME_FORMAT = "%Y%m%d %H%M%S%f"  # HistData ticks: "YYYYMMDD HHMMSSfff"


@contextmanager
def _open_text_stream(source: SourceFile) -> Generator[io.TextIOBase]:
    if source.is_zip and source.csv_name:
        with zipfile.ZipFile(source.path) as zf, zf.open(source.csv_name) as raw:
            yield io.TextIOWrapper(raw, encoding="ascii")
    else:
        with open(source.path, "r", encoding="ascii") as f:
            yield f


def iter_tick_chunks(
    source: SourceFile, chunksize: int, price_col: str
) -> Iterator[pd.DataFrame]:
    """Yield DataFrames of at most `chunksize` ticks, each with a DatetimeIndex
    and a single float32 `price` column, ready to hand to the aggregator."""
    dtypes = {"bid": "float32", "ask": "float32", "volume": "int32"}
    with _open_text_stream(source) as stream:
        reader = pd.read_csv(
            stream,
            names=COLUMN_NAMES,
            header=None,
            dtype=dtypes,
            chunksize=chunksize,
            engine="c",
        )
        for chunk in reader:
            chunk["datetime"] = pd.to_datetime(
                chunk["datetime_raw"], format=DATETIME_FORMAT
            )
            chunk.set_index("datetime", inplace=True)
            chunk["price"] = _compute_price(chunk, price_col)
            yield chunk[["price"]]


def _compute_price(chunk: pd.DataFrame, price_col: str) -> pd.Series:
    if price_col == "bid":
        return chunk["bid"]
    if price_col == "ask":
        return chunk["ask"]
    if price_col == "mid":
        return (chunk["bid"] + chunk["ask"]) / 2.0
    raise ValueError(f"Unknown price column: {price_col!r} (expected bid/ask/mid)")
