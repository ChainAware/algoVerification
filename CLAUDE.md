# ChainAwareVerification

Batch fraud verification tool. Calls the ChainAware `/fraud/check` API for every address in a CSV and writes scored results.

## Project layout

```
tests/
  batch/
    fraud_verification.py   # main script
    output/                 # results land here (gitignored)
  testdata/
    knownScam.csv           # ground-truth scam addresses from CryptoScamDB
.env.example                # required env vars
requirements.txt            # python-dotenv, requests
```

## Environment

Copy `.env.example` to `.env` and set:
- `CHAINAWARE_API_KEY` — required
- `CHAINAWARE_API_URL` — defaults to `https://api.chainaware.ai/api`

## Running

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
venv/bin/python tests/batch/fraud_verification.py --limit 10
```

## Output CSV columns

`address, chain, status, prob_fraud, elapsed_s`

Results go to `tests/batch/output/<input_stem>_results.csv`. A `.log` file is written alongside it. The run resumes automatically if interrupted — already-processed addresses are skipped.

## API call

`POST /fraud/check` with `{"walletAddress", "network", "calculate": true}`.
Retries on 429 (rate limit) and 5xx with exponential backoff. Max 3 retries.

## Key decisions

- No async — the API is called synchronously, one address at a time.
- `calculate: true` on every call — always requests a fresh score, not a cached result.
- Chain map: `BSC` → `BNB`, everything else passed through as-is.
