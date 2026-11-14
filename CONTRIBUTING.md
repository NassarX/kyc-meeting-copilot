# Contributing

## Setup

```bash
uv sync --extra viewer          # add --extra audio on Apple Silicon
uvx pre-commit install          # optional: runs lint and the secret scan before each commit
```

## How a change lands

1. **Branch from `main`**, short-lived, named by kind: `feat/…`, `fix/…`, `docs/…`, `test/…`, `refactor/…`, `chore/…`, `ci/…`.
2. **Commit as often as you like** on the branch; those commits are squashed away.
3. **Open a pull request.** Its title is a [Conventional Commit](https://www.conventionalcommits.org/) (`feat(rules): add …`, `fix(extract): …`): it becomes the one commit on `main`, so write it for a reader of `git log`. The description says what changed, why, and how it was checked.
4. **Checks must pass:** tests on Python 3.12 and 3.13, every case consistent with the rules, lint, a secret scan over the whole history, and the PR title.
5. **Squash and merge.** `main` stays linear: one commit per change, each one green. The branch is deleted on merge.

`main` is protected: no direct pushes, no force pushes, no merge without passing checks.

## Releases

Versions follow [semantic versioning](https://semver.org/). To release, move the `Unreleased` notes in `CHANGELOG.md` under the new version in a PR, merge it, then tag `main` (`git tag -a v0.2.0 -m "v0.2.0"` and push the tag) and publish a GitHub release from the tag.

## Ground rules

- **Synthetic data only.** No real people, clients, companies, documents or recordings, anywhere: code, cases, tests, issues.
- **Rules need a public source.** The loader refuses anything else (`src/kyc_copilot/rules/`).
- **The model proposes; code decides.** Changes that let a model decide a flag, a contradiction or a case state need a decision record in `docs/decisions.md` first.
- **No paid calls in tests.** Tests use fakes; a change to extraction, rules or grading comes with a scorecard from `kyc-eval` and its cost.
- **Report results as they come out.** Don't change a case or the grader after seeing a run's results; fix the pipeline, or record the deviation (see `eval/preregistration.md`).
- **Secrets** go in `.env` (git-ignored), never in code or history.
