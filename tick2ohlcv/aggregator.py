from __future__ import annotations

import csv
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, cast

import numpy as np
import pandas as pd

# accept both 'h' and "H"...
_ALIAS_MAP = {"H": "h", "T": "min", "S": "s", "L": "ms", "U": "us", "N": "ns"}


def normalize_freq(freq: str) -> str:
    number = "".join(ch for ch in freq if ch.isdigit())
    unit = freq[len(number):]
    unit = _ALIAS_MAP.get(unit, _ALIAS_MAP.get(unit.upper(), unit))
    return f"{number}{unit}"


@dataclass
class _Bar:
    open_time: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: int  # tick count

    def as_row(self) -> list:
        ts = self.open_time.value // 10**9
        return [ts, round(self.open, 6), round(self.high, 6), round(self.low, 6),
                round(self.close, 6), self.volume]


class OHLCVAggregator:
    HEADER: ClassVar[list[str]] = ["ts", "open", "high", "low", "close", "tick_volume"]

    def __init__(self, freq: str, output_dir: Path, flush_every: int = 50_000):
        self.freq = normalize_freq(freq)
        self.output_dir = output_dir
        self.flush_every = flush_every
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._current: _Bar | None = None
        self._write_buffer: list[tuple[str, list]] = []
        self._bars_written = 0
        self._files = ExitStack()
        self._writers: dict[str, Any] = {}

    @property
    def bars_written(self) -> int:
        return self._bars_written

    def process(self, chunk: pd.DataFrame) -> None:
        """Feed one time-ordered chunk (DatetimeIndex, single 'price' column)."""
        if chunk.empty:
            return

        index = cast(pd.DatetimeIndex, chunk.index)
        bar_times = index.floor(self.freq).to_numpy()
        prices = chunk["price"].to_numpy()

        # bar_times is sorted, so a bar's ticks are always a contiguous
        # slice -- find where it changes instead of doing a full groupby.
        boundaries = np.flatnonzero(bar_times[1:] != bar_times[:-1]) + 1
        starts = np.concatenate(([0], boundaries))
        ends = np.concatenate((boundaries, [len(bar_times)]))

        for start, end in zip(starts, ends):
            bar_time = pd.Timestamp(bar_times[start])
            segment = prices[start:end]
            if self._current is None:
                self._current = self._new_bar(bar_time, segment)
            elif bar_time == self._current.open_time:
                self._update_bar(self._current, segment)
            else:
                self._flush_bar()
                self._current = self._new_bar(bar_time, segment)

        if len(self._write_buffer) >= self.flush_every:
            self._drain_buffer()

    def close(self) -> None:
        if self._current is not None:
            self._flush_bar()
        self._drain_buffer()
        self._files.close()

    # -- internals ----------------------------------------------------

    @staticmethod
    def _new_bar(bar_time: pd.Timestamp, segment: np.ndarray) -> _Bar:
        return _Bar(
            open_time=bar_time,
            open=float(segment[0]),
            high=float(segment.max()),
            low=float(segment.min()),
            close=float(segment[-1]),
            volume=len(segment),
        )

    @staticmethod
    def _update_bar(bar: _Bar, segment: np.ndarray) -> None:
        bar.high = max(bar.high, float(segment.max()))
        bar.low = min(bar.low, float(segment.min()))
        bar.close = float(segment[-1])
        bar.volume += len(segment)

    def _flush_bar(self) -> None:
        assert self._current is not None
        year_month = self._current.open_time.strftime("%Y-%m")
        self._write_buffer.append((year_month, self._current.as_row()))
        self._bars_written += 1
        self._current = None

    def _drain_buffer(self) -> None:
        for year_month, row in self._write_buffer:
            self._writer_for(year_month).writerow(row)
        self._write_buffer.clear()

    def _writer_for(self, year_month: str) -> Any:
        writer = self._writers.get(year_month)
        if writer is None:
            fh = self._files.enter_context(open(self.output_dir / f"{year_month}.csv", "w", newline=""))
            writer = csv.writer(fh)
            writer.writerow(self.HEADER)
            self._writers[year_month] = writer
        return writer
