# tick2ohlcv

Turns HistData.com ASCII tick exports into OHLCV bars. Streams straight
out of the `.zip` files with bounded memory, handles any number of
symbols and timeframes in one pass, and writes output split by month so
you're never looking at one giant CSV.

## Setup

Copy `run.py` and the `tick2ohlcv/` folder into your project root, next
to your existing `data/` directory. Nothing about your data layout needs
to change — discovery works off filenames, following the vendor's own
convention:

```
HISTDATA_COM_ASCII_<SYMBOL>_T<YYYYMM>.zip
    containing DAT_ASCII_<SYMBOL>_T_<YYYYMM>.csv
```

Requires `pandas` and `numpy` (`pip install pandas numpy`).

```bash
pip install -r requirements
```

## Usage

```bash
# everything under ./data, 1-minute and 5-minute bars, mid price
python run.py --timeframes 1min,5min,15T

# one symbol, hourly bars from the bid price, custom paths
python run.py --data-dir /mnt/fx_data --output-dir /mnt/fx_ohlcv \
              --symbols EURUSD --timeframes 1h --price bid

# a few symbols, restricted to a period range (inclusive, YYYYMM)
python run.py --symbols EURUSD,GBPUSD --start 202511 --end 202608
```

Every flag also has an env var equivalent (`TICK2OHLCV_` prefix), so the
same script runs unattended in a cron job or container without touching
the command line:

```bash
export TICK2OHLCV_DATA_DIR=/mnt/fx_data
export TICK2OHLCV_TIMEFRAMES=1min,15min,1h
python run.py
```

CLI flags win over env vars, which win over the built-in defaults.

## Output layout

```
output/
└── EURUSD/
    ├── 1min/
    │   ├── 2025-11.csv
    │   └── 2025-12.csv
    └── 1h/
        ├── 2025-11.csv
        └── 2025-12.csv
```

Each file is `datetime,open,high,low,close,volume`. A bar is filed under
the month its *open* timestamp falls in — so the one bar that straddles
midnight on the 1st goes with the earlier month, same as most vendors do
it. `volume` is tick count, not real trade volume — HistData's tick
files don't carry that (the 4th column is always 0), and tick count is
the standard stand-in.

## Accepted timeframes

`--timeframes` takes a comma-separated list of `<number><unit>` values.
Both the old pandas spellings and the new ones work interchangeably:

| Unit | Meaning | Examples |
|---|---|---|
| `min` or `T` | minutes | `1min` / `1T`, `5min` / `5T`, `15min` / `15T`, `30min` / `30T` |
| `h` or `H` | hours | `1h` / `1H`, `4h` / `4H` |
| `D` | calendar days | `1D` |
| `W` | weeks | `1W` |
| `s` or `S` | seconds | `30s` / `30S` (only useful on very liquid periods) |

So `--timeframes 1min,5min,1H,1D` and `--timeframes 1min,5min,1h,1D` are
the same request. Anything pandas' `resample()` understands as an offset
alias will work here, this table just covers what you'll actually use
for tick data.

## How it stays memory-safe

Two things keep this from ever loading a full month into RAM:

- Ticks are read straight out of the zip member via `pandas.read_csv(...,
  chunksize=...)`, in chunks of `--chunksize` rows (1,000,000 by default,
  float32). Nothing gets extracted to disk first.
- The aggregator doesn't resample chunk by chunk — it's a running
  accumulator that holds exactly one in-progress bar per timeframe and
  updates it tick by tick. When a bar closes it gets buffered for a
  batched write, then the buffer clears. This is also what makes bars
  spanning a chunk or file boundary come out correct instead of getting
  split in two.
