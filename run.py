#!/usr/bin/env

from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

from tick2ohlcv.aggregator import OHLCVAggregator
from tick2ohlcv.discovery import discover, filter_periods, filter_symbols
from tick2ohlcv.io_utils import iter_tick_chunks

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tick2ohlcv")


def env(name: str, default: str) -> str:
    return os.environ.get(f"TICK2OHLCV_{name}", default)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert tick data to OHLCV bars, symbol by symbol.")
    p.add_argument("--data-dir", type=Path, default=Path(env("DATA_DIR", "data")),
                    help="Root folder to scan for *.zip / *.csv tick exports (searched recursively).")
    p.add_argument("--output-dir", type=Path, default=Path(env("OUTPUT_DIR", "output")),
                    help="Root folder to write <symbol>/<timeframe>/<year-month>.csv into.")
    p.add_argument("--symbols", type=lambda s: s.split(","), default=env("SYMBOLS", "all").split(","),
                    help="Comma-separated symbols (e.g. EURUSD,GBPUSD) or 'all' to process every symbol found.")
    p.add_argument("--timeframes", type=lambda s: s.split(","), default=env("TIMEFRAMES", "1min").split(","),
                    help="Comma-separated bar sizes, e.g. 1min,5min,15min,1h,1D. See README for the full list.")
    p.add_argument("--price", choices=["bid", "ask", "mid"], default=env("PRICE", "mid"),
                    help="Which price to bar: bid, ask, or mid ((bid+ask)/2). Default: mid.")
    p.add_argument("--chunksize", type=int, default=int(env("CHUNKSIZE", "1000000")),
                    help="Ticks read per chunk. Lower = less memory, more overhead. Default: 1,000,000.")
    p.add_argument("--start", default=env("START", "") or None, help="Earliest period to include, YYYYMM.")
    p.add_argument("--end", default=env("END", "") or None, help="Latest period to include, YYYYMM.")
    return p.parse_args()


def run(args: argparse.Namespace) -> None:
    if not args.data_dir.exists():
        raise SystemExit(f"Data directory not found: {args.data_dir}")

    all_files = discover(args.data_dir)
    if not all_files:
        raise SystemExit(f"No HistData-style tick archives found under {args.data_dir}")

    selected = filter_symbols(all_files, args.symbols)
    log.info("Symbols to process: %s", ", ".join(selected))

    for symbol, sources in selected.items():
        sources = filter_periods(sources, args.start, args.end)
        if not sources:
            log.warning("[%s] no files in requested period range, skipping", symbol)
            continue

        log.info("[%s] %d monthly file(s): %s", symbol, len(sources), [s.period for s in sources])

        aggregators = {
            tf: OHLCVAggregator(tf, args.output_dir / symbol / tf)
            for tf in args.timeframes
        }

        t0 = time.time()
        total_ticks = 0
        try:
            for source in sources:
                log.info("[%s] reading %s", symbol, source.path.name)
                for chunk in iter_tick_chunks(source, args.chunksize, args.price):
                    total_ticks += len(chunk)
                    for agg in aggregators.values():
                        agg.process(chunk)
        finally:
            for tf, agg in aggregators.items():
                agg.close()
                log.info("[%s] %s -> %d bars -> %s", symbol, tf, agg.bars_written, agg.output_dir)

        elapsed = time.time() - t0
        log.info("[%s] done: %d ticks in %.1fs (%.0f ticks/sec)", symbol, total_ticks, elapsed,
                  total_ticks / elapsed if elapsed > 0 else 0)


if __name__ == "__main__":
    run(parse_args())
