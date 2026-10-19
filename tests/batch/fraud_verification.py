"""
Batch fraud verification: run POST /fraud/check against a CSV of addresses
and write results to tests/batch/output/.

Input CSV columns: address, chain  (chain values: ETH, BSC, POLYGON)

Supports resume: if the output CSV already exists, addresses already present
are skipped so the run can be interrupted and restarted safely.

Usage:
    venv/bin/python tests/batch/fraud_verification.py --input tests/testdata/knownScam.csv
    venv/bin/python tests/batch/fraud_verification.py --input tests/testdata/knownScam.csv --limit 50
    venv/bin/python tests/batch/fraud_verification.py --input tests/testdata/knownScam.csv --output tests/batch/output/custom.csv
"""

import argparse
import csv
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

HERE       = Path(__file__).parent
ROOT       = HERE.parent.parent
OUTPUT_DIR = HERE / "output"
INPUT_FILE = HERE.parent / "testdata" / "knownScam.csv"

_FMT    = "%(asctime)s [%(levelname)s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# CSV chain value → API network code
CHAIN_MAP = {"ETH": "ETH", "BNB": "BNB", "BSC": "BNB", "POLYGON": "POLYGON",
             "BASE": "BASE", "ARB": "ARB", "OP": "OP"}

_TIMEOUT     = 30.0
_MAX_RETRIES = 3
_BACKOFF_429 = 2.0
_BACKOFF_5XX = 10.0
_RETRY_5XX   = {502, 503, 504}


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(exist_ok=True)
    fmt = logging.Formatter(_FMT, datefmt=_DATEFMT)
    fh  = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh  = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger = logging.getLogger("verification")
    logger.setLevel(logging.INFO)
    logger.addHandler(sh)
    logger.addHandler(fh)
    return logger


log: logging.Logger = None


def _api_headers() -> dict:
    key = os.environ.get("CHAINAWARE_API_KEY", "")
    if not key:
        print("ERROR: CHAINAWARE_API_KEY not set. Copy .env.example to .env and add your key.", file=sys.stderr)
        sys.exit(1)
    return {"x-api-key": key, "Content-Type": "application/json"}


def _base_url() -> str:
    return os.environ.get("CHAINAWARE_API_URL", "https://api.chainaware.ai/api").rstrip("/")


def fraud_check(address: str, network: str) -> dict:
    url     = f"{_base_url()}/fraud/check"
    payload = {"walletAddress": address, "network": network, "calculate": True}
    headers = _api_headers()

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
        except requests.exceptions.Timeout:
            if attempt == _MAX_RETRIES:
                log.warning("Timeout for %s after %d retries", address, _MAX_RETRIES)
                return {"status": "Error", "prob_fraud": "NA"}
            time.sleep(_BACKOFF_5XX * (2 ** attempt))
            continue
        except requests.exceptions.ConnectionError as exc:
            if attempt == _MAX_RETRIES:
                log.warning("Connection error for %s after %d retries: %s", address, _MAX_RETRIES, exc)
                return {"status": "Error", "prob_fraud": "NA"}
            time.sleep(_BACKOFF_5XX * (2 ** attempt))
            continue
        except requests.exceptions.RequestException as exc:
            log.warning("Request error for %s: %s", address, exc)
            return {"status": "Error", "prob_fraud": "NA"}

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else _BACKOFF_429 * (2 ** attempt)
            log.warning("Rate limited — waiting %.0fs", wait)
            time.sleep(wait)
            continue

        if resp.status_code in _RETRY_5XX:
            if attempt == _MAX_RETRIES:
                log.warning("HTTP %s for %s after %d retries", resp.status_code, address, _MAX_RETRIES)
                return {"status": "Error", "prob_fraud": "NA"}
            time.sleep(_BACKOFF_5XX * (2 ** attempt))
            continue

        if resp.status_code == 400:
            try:
                body = resp.json()
                if "contract address" in body.get("error", "").lower():
                    return {"status": "contract", "prob_fraud": "NA"}
            except Exception:
                pass
            return {"status": "Error", "prob_fraud": "NA"}

        if resp.status_code != 200:
            log.warning("HTTP %s for %s: %s", resp.status_code, address, resp.text[:120])
            return {"status": "Error", "prob_fraud": "NA"}

        try:
            data = resp.json()
        except Exception:
            return {"status": "Error", "prob_fraud": "NA"}

        if data.get("error"):
            if "contract address" in data["error"].lower():
                return {"status": "contract", "prob_fraud": "NA"}
            log.warning("API error for %s: %s", address, data["error"])
            return {"status": "Error", "prob_fraud": "NA"}

        status = data.get("status") or data.get("Status", "Unknown")
        prob   = data.get("probabilityFraud") or data.get("ProbabilityFraud", "NA")
        return {"status": status, "prob_fraud": prob}

    return {"status": "Error", "prob_fraud": "NA"}


def load_already_done(output_path: Path) -> set:
    done = set()
    if not output_path.exists() or output_path.stat().st_size == 0:
        return done
    try:
        with open(output_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add(row["address"].lower())
        log.info("Resume: %d addresses already in %s, skipping.", len(done), output_path.name)
    except Exception as e:
        log.warning("Could not read existing output file, starting fresh: %s", e)
    return done


def run(args):
    input_file  = Path(args.input).resolve()
    output_path = Path(args.output).resolve() if args.output else _default_output(input_file, args.chain, args.snapshot)
    log_path    = output_path.with_suffix(".log")

    global log
    log = setup_logging(log_path)
    log.info("Log: %s", log_path)
    log.info("Loading input from %s", input_file)

    try:
        wallets = _load_input(input_file, args.chain)
    except FileNotFoundError:
        log.error("Input file not found: %s", input_file)
        sys.exit(1)
    except Exception as exc:
        log.error("Failed to read input file: %s", exc)
        sys.exit(1)
    log.info("Loaded %d addresses from %s", len(wallets), input_file.name)

    chain_counts: dict[str, int] = {}
    for w in wallets:
        chain_counts[w["chain"]] = chain_counts.get(w["chain"], 0) + 1
    for chain, count in sorted(chain_counts.items()):
        log.info("  %s: %d addresses", chain, count)

    done       = load_already_done(output_path)
    to_process = [w for w in wallets if w["address"].lower() not in done]
    if args.limit is not None:
        to_process = to_process[:args.limit]

    if not to_process:
        log.info("All addresses already processed — nothing to do.")
        return

    log.info("Processing %d addresses (skipped %d already done)", len(to_process), len(done))

    is_new_file = not output_path.exists() or output_path.stat().st_size == 0
    csv_fields  = ["address", "chain", "status", "prob_fraud", "elapsed_s"]

    try:
        out_file = open(output_path, "a", newline="", encoding="utf-8")
    except OSError as exc:
        log.error("Cannot open output file %s: %s", output_path, exc)
        sys.exit(1)

    with out_file as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        if is_new_file:
            writer.writeheader()

        for i, wallet in enumerate(to_process, 1):
            addr  = wallet["address"]
            chain = wallet["chain"]

            t0      = time.time()
            result  = fraud_check(addr, chain)
            elapsed = time.time() - t0

            row = {"address": addr, "chain": chain}
            row["status"]     = result["status"]
            row["prob_fraud"] = result["prob_fraud"]
            row["elapsed_s"]  = round(elapsed, 2)

            try:
                writer.writerow(row)
                f.flush()
            except OSError as exc:
                log.error("Write error at row %d (%s): %s — aborting", i, addr, exc)
                sys.exit(1)

            done.add(addr.lower())

            log.info("[%d/%d] %s  chain=%s  status=%s  prob=%s  (%.1fs)",
                     i, len(to_process), addr, chain, result["status"], result["prob_fraud"], elapsed)

    log.info("Done. Results written to %s", output_path)
    _print_summary(output_path)


def _load_input(input_file: Path, chain_override: str | None):
    wallets = []
    with open(input_file, newline="", encoding="utf-8") as f:
        reader   = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        addr_col = "address" if "address" in fieldnames else "addres"
        for row in reader:
            addr  = row[addr_col].strip()
            chain = chain_override.upper() if chain_override else row["chain"].strip().upper()
            if not addr:
                continue
            wallets.append({"address": addr, "chain": CHAIN_MAP.get(chain, chain)})
    return wallets


def _default_output(input_file: Path, chain_override: str | None, snapshot: bool) -> Path:
    base_dir = OUTPUT_DIR / datetime.now().strftime("%y%m%d-%H%M") if snapshot else OUTPUT_DIR
    base_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{chain_override}" if chain_override else ""
    return base_dir / f"{input_file.stem}{suffix}_results.csv"


def _print_summary(output_path: Path):
    statuses: dict[str, int] = {}
    with open(output_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            statuses[row["status"]] = statuses.get(row["status"], 0) + 1
    total = sum(statuses.values())
    log.info("--- Status breakdown ---")
    for status, count in sorted(statuses.items(), key=lambda x: -x[1]):
        log.info("  %-20s %5d", status, count)
    log.info("  %-20s %5d", "TOTAL", total)


def main():
    parser = argparse.ArgumentParser(
        description="Batch fraud verification — calls POST /fraud/check for each address in a CSV"
    )
    parser.add_argument("--input",    default=str(INPUT_FILE),
                        help=f"Input CSV (default: {INPUT_FILE.name})")
    parser.add_argument("--chain",    default=None, choices=list(CHAIN_MAP.keys()),
                        help="Override chain for all addresses (default: use chain column)")
    parser.add_argument("--output",   default=None,
                        help="Output CSV path (default: auto-derived from input + chain)")
    parser.add_argument("--limit",    type=int, default=None,
                        help="Max addresses to process (for testing)")
    parser.add_argument("--snapshot", action="store_true",
                        help="Store CSV and log in a timestamped subfolder output/YYMMDD-HHMM/")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
