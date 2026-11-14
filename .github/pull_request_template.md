## What and why

<!-- One or two sentences: what changes, and the reason. The PR title becomes the commit message on main. -->

## How it was checked

- [ ] `uv run pytest -q` passes
- [ ] `uv run kyc-eval run --pipeline gold` reports no case problems
- [ ] `uv run ruff check src tests cases eval` passes
- [ ] If extraction, rules or grading changed: a scorecard is attached or linked, and its cost stated

## Data

- [ ] Synthetic data only: no real people, clients, companies or documents
- [ ] New rules cite a public source
