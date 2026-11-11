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

## Further Reading

- [Fraud Detector Guide](https://chainaware.ai/blog/chainaware-fraud-detector-guide/) — How `predictive_fraud` works: inputs, outputs, thresholds, and use cases
- [$284M+ Rug Pulls on PancakeSwap V2](https://chainaware.ai/blog/rugpull-detector-v3-pancakev2-2026/) — Real-world accuracy benchmark: 90.1% detection rate across 103,695 rug pull events
- [Token Audit: 10,000 CoinGecko Token Results](https://chainaware.ai/blog/token-audit-10000-coingecko-results/) — 55% HIGH RISK; 127 automated checks via `run_token_audit`
- [Token Audit at Scale: 15,000 EVM Tokens](https://chainaware.ai/blog/token-audit-15000-coingecko-coinmarketcap-2026/) — 57.7% HIGH RISK across CoinGecko + CoinMarketCap tokens
- [Complete Product Guide](https://chainaware.ai/blog/chainaware-ai-products-complete-guide/) — Overview of all ChainAware tools, networks, and coverage
- [Fraud Detection Docs](https://chainaware.ai/learn/for-individuals/fraud-detector.html) — How the fraud detector works, what the score means, and how to interpret results
- [AML & KYC Compliance](https://chainaware.ai/learn/use-cases/aml-kyc-compliance.html) — AML screening, MiCA obligations, and transaction monitoring use cases
- [Prediction MCP](https://chainaware.ai/learn/prediction-mcp/) — Full tool reference for predictive_fraud and all 14 MCP tools
