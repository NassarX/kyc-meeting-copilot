# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- A fact quoting a transcript segment that Whisper scored under 0.7 on average now gets "listen to the clip": Whisper invents text in long silences, and a quote of it passes the quote check ([evaluation](docs/evaluation.md#catching-misheard-values)).
- Contribution workflow: pull requests with squash merges, a Conventional Commit check on PR titles, lint and a full-history secret scan in CI, Dependabot, pre-commit hooks, a PR template and `CONTRIBUTING.md`.

## [0.1.0] - 2026-11-14

First public version: a proof of concept on synthetic data.

### Added
- Extraction with Claude (structured output), every fact quoting its words; quotes checked and located by code, one retry, then rejected and counted.
- Code that decides: reconcile against the bank's file (contradictions never resolved automatically), plausibility doubts, transcriber doubt, nine compliance rules with public sources, gaps.
- Hardening adapted from gbrain (MIT): prompt-injection guard, name-variant notes, bounded windows.
- Local transcription with Whisper, keeping word timings and confidence; device transcripts readable for comparison.
- `kyc-check` for one meeting, `kyc-eval` for the evaluation harness, `kyc-viewer` for the web app with confirm-by-ear and a downloadable report.
- Six public synthetic cases (C01, D01–D05) with hand-written gold, five fresh scored runs, and the preregistration.
- Case state machine and append-only store, foundation for the human sign-off steps.

[Unreleased]: https://github.com/NassarX/kyc-meeting-copilot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/NassarX/kyc-meeting-copilot/releases/tag/v0.1.0
