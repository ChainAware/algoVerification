# ChainAware Verification

Batch fraud verification tool that runs the [ChainAware](https://chainaware.ai) fraud detection API against a CSV of wallet addresses and writes scored results to CSV.

## Dataset

`tests/testdata/knownScam.csv` contains known scam wallet addresses sourced from [CryptoScamDB](https://cryptoscamdb.org/).

CryptoScamDB is an open-source database of cryptocurrency scam addresses, phishing domains, and fraudulent projects. It is community-maintained and widely used as a reference dataset for blockchain security research. The database aggregates reports of scam wallets across Ethereum and other EVM-compatible chains.

This dataset is used to validate the ChainAware fraud detection pipeline: every address in it should score as fraudulent, making it a useful ground-truth benchmark.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set CHAINAWARE_API_KEY
```

Get your API key at [chainaware.ai/profile](https://chainaware.ai/profile).

## Running

```bash
# full run against the default dataset
venv/bin/python tests/batch/fraud_verification.py

# limit to the first 50 addresses (useful for testing)
venv/bin/python tests/batch/fraud_verification.py --limit 50

# custom input file
venv/bin/python tests/batch/fraud_verification.py --input path/to/addresses.csv

# override chain for all rows (ignores the chain column)
venv/bin/python tests/batch/fraud_verification.py --chain ETH

# save output to a timestamped subfolder
venv/bin/python tests/batch/fraud_verification.py --snapshot
```

### Input CSV format

| column  | required | values                        |
|---------|----------|-------------------------------|
| address | yes      | wallet address                |
| chain   | yes      | ETH, BSC, BNB, POLYGON, BASE, ARB, OP |

### Output

Results are written to `tests/batch/output/<input_stem>_results.csv`:

| column     | description                          |
|------------|--------------------------------------|
| address    | wallet address                       |
| chain      | network code sent to the API         |
| status     | fraud verdict returned by the API    |
| prob_fraud | fraud probability (0–1) or NA        |
| elapsed_s  | API call duration in seconds         |

A `.log` file is written alongside the output CSV with the full run log.

## Resume

If the run is interrupted it can be restarted with the same command. Addresses already present in the output CSV are skipped automatically, so the run continues from where it stopped.
