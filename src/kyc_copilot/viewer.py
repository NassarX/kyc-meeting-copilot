"""Demo viewer: a local web app over kyc_copilot.run.process (design: DESIGN.md).

    kyc-viewer               # http://127.0.0.1:8000, this machine only
    kyc-viewer --lan         # https on the local network, for Safari on an iPad (the mic needs HTTPS)

For a link others open (handover): set VIEWER_PASSWORD (one shared password, HTTP Basic) and VIEWER_BUDGET_USD
(total new spend the viewer may make, kept across restarts in .viewer-spend.json; cached runs stay free, so
the samples keep working after the budget is used up). How to host it: viewer/README.md.

Inputs: a pasted transcript, an uploaded or recorded audio file, or the sample case (C01 with its bank file). Audio is
transcribed on this machine and kept in a local folder so each key figure can be played back for confirmation (confirm-by-ear,
layer 2). The API key stays on the server. Synthetic demo data only; there is no login, so --lan is for a trusted
network during a demo.

Install the extras first: `uv sync --extra audio --extra viewer`.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from kyc_copilot.eval.case_format import load_case
from kyc_copilot.eval.harness import DEFAULT_CASES
from kyc_copilot.rules import load_bounce_reasons
from kyc_copilot.extract import SpendCapReached
from kyc_copilot.run import parse_transcript, process
from kyc_copilot.taxonomy import load_taxonomy

POC = Path(__file__).parents[2]
WEB = POC / "viewer"
AUDIO_DIR = POC / ".viewer-audio"
CERTS = POC / ".certs"
SPEND_FILE = POC / ".viewer-spend.json"
SAMPLE_DIR = WEB / "samples"
RUN_CAP = 0.5  # USD per run
SAMPLE_DATE = date(2026, 11, 9)  # the meeting date the D samples are written against
SAMPLE = "C01"
# id, title, one line on what it shows; C01 borrows its case's bank file, D01-D05 are transcripts in SAMPLE_DIR
SAMPLES = [
    ("C01", "Isabel Marchetti-Okonkwo", "Business sale, a foundation, and a name spelt differently from the bank's file"),
    ("D01", "Ingrid Halvorsen-Matos", "A clean meeting: inheritance and salary, nothing to flag"),
    ("D02", "Dariusz Kowalczyk-Amari", "A sister in government, played down, and a tax residence that changes"),
    ("D03", "Aurelio Bastien-Nakamura", "A Jersey company under a Liechtenstein foundation; date of birth never said"),
    ("D04", "Beatriz Moreira Lindgren", "Funding larger than the stated wealth, and a sale dated in the future"),
    ("D05", "Nikolaos Papadakis-Rowe", "A messy meeting: interruptions, a health aside, and an attempt to skip checks"),
]
_AUDIO_ID = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{2,5}$")


def _default_extractor(cap_usd: float):
    from kyc_copilot.extract import ModelExtractor
    return ModelExtractor(load_taxonomy(), cap_usd=cap_usd)


def _default_transcribe(path: Path, day: date):
    from kyc_copilot.capture import transcribe
    return transcribe(path, day)


class Budget:
    """New spend the viewer may make in total, kept in a small JSON file so a restart doesn't reset it."""
    def __init__(self, limit_usd: float | None, path: Path):
        self.limit, self.path = limit_usd, path

    @property
    def spent(self) -> float:
        try:
            return float(json.loads(self.path.read_text())["spent_usd"])
        except (OSError, ValueError, KeyError):
            return 0.0

    def run_cap(self) -> float:
        return RUN_CAP if self.limit is None else max(0.0, min(RUN_CAP, self.limit - self.spent))

    def add(self, usd: float) -> None:
        if usd:
            self.path.write_text(json.dumps({"spent_usd": round(self.spent + usd, 4)}))


def create_app(extractor=_default_extractor, transcribe=_default_transcribe, audio_dir: Path = AUDIO_DIR,
               password: str | None = None, budget_usd: float | None = None,
               spend_file: Path = SPEND_FILE) -> FastAPI:
    app = FastAPI(title="kyc-presubmit demo viewer", docs_url=None, redoc_url=None)
    budget = Budget(budget_usd, spend_file)

    if password:
        @app.middleware("http")
        async def gate(request: Request, call_next):
            given = ""
            scheme, _, cred = request.headers.get("authorization", "").partition(" ")
            if scheme.lower() == "basic":
                try:
                    given = base64.b64decode(cred).decode().partition(":")[2]
                except ValueError:
                    pass
            if not secrets.compare_digest(given.encode(), password.encode()):
                return JSONResponse({"detail": "password required"}, status_code=401,
                                    headers={"WWW-Authenticate": 'Basic realm="kyc-presubmit demo"'})
            return await call_next(request)

    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")

    def check(heard, borrowed=None):
        try:
            result = process(heard, borrow=borrowed, extractor=extractor(budget.run_cap()))
        except SpendCapReached:
            raise HTTPException(402, "The demo's spending budget is used up. The sample meetings still work; a new "
                                     "meeting needs the owner to raise the budget.") from None
        budget.add(result.cost_usd)
        return {**result.to_dict(), "meeting_date": heard.meeting_date.isoformat()}

    def borrow(case_id: str | None):
        if not case_id:
            return None
        if not re.fullmatch(r"[A-Z]\d{2}", case_id) or not (DEFAULT_CASES / f"{case_id}.yaml").exists():
            raise HTTPException(400, f"unknown case {case_id!r}")
        taxonomy = load_taxonomy()
        return load_case(DEFAULT_CASES / f"{case_id}.yaml", taxonomy, load_bounce_reasons(taxonomy))

    @app.get("/")
    def page():
        return FileResponse(WEB / "index.html")

    @app.post("/api/run")
    def run(transcript: str = Form(""), meeting_date: str = Form(""), case: str = Form(""),
            audio: UploadFile | None = File(None)):
        try:
            day = date.fromisoformat(meeting_date) if meeting_date else date.today()
        except ValueError:
            raise HTTPException(400, "meeting_date must be YYYY-MM-DD") from None
        audio_url = None
        if audio is not None and audio.filename:
            ext = (Path(audio.filename).suffix.lower().lstrip(".") or "m4a")
            ext = ext if re.fullmatch(r"[a-z0-9]{2,5}", ext) else "m4a"
            audio_dir.mkdir(parents=True, exist_ok=True)
            name = f"{uuid.uuid4().hex}.{ext}"
            path = audio_dir / name
            path.write_bytes(audio.file.read())
            heard = transcribe(path, day)
            audio_url = f"/api/audio/{name}"
        elif transcript.strip():
            try:
                heard = parse_transcript(transcript, day)
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
        else:
            raise HTTPException(400, "give a transcript or an audio file")
        return {**check(heard, borrow(case or None)), "audio_url": audio_url, "case": case or None, "sample": None}

    @app.get("/api/samples")
    def samples():
        return [{"id": i, "title": t, "blurb": b} for i, t, b in SAMPLES]

    @app.post("/api/sample")
    @app.post("/api/sample/{sample_id}")
    def sample(sample_id: str = SAMPLE):
        if sample_id not in {i for i, _, _ in SAMPLES}:
            raise HTTPException(404, f"no sample {sample_id!r}")
        if sample_id.startswith("C"):
            c = borrow(sample_id)
            return {**check(c.transcript, c), "audio_url": None, "case": sample_id, "sample": sample_id}
        (path,) = SAMPLE_DIR.glob(f"{sample_id}-*.txt")
        heard = parse_transcript(path.read_text(encoding="utf-8"), SAMPLE_DATE, path.name)
        return {**check(heard), "audio_url": None, "case": None, "sample": sample_id}

    @app.get("/api/audio/{name}")
    def audio_file(name: str):
        path = audio_dir / name
        if not _AUDIO_ID.fullmatch(name) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    return app


def _lan_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # no packet is sent; this picks the outgoing interface
        return s.getsockname()[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kyc-viewer", description="Run the demo viewer.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--lan", action="store_true", help="serve HTTPS on the local network (for an iPad)")
    args = ap.parse_args(argv)
    import uvicorn
    password = os.environ.get("VIEWER_PASSWORD") or None
    budget = float(os.environ["VIEWER_BUDGET_USD"]) if os.environ.get("VIEWER_BUDGET_USD") else None
    app = create_app(password=password, budget_usd=budget)
    guard = (f"password {'on' if password else 'OFF'}, budget "
             + (f"${budget:.2f} (${Budget(budget, SPEND_FILE).spent:.2f} spent)" if budget is not None else "none"))
    if not args.lan:
        print(f"Viewer: http://127.0.0.1:{args.port}  ({guard})")
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        return 0
    ip = _lan_ip()
    CERTS.mkdir(exist_ok=True)
    cert, key = CERTS / "cert.pem", CERTS / "key.pem"
    if not cert.exists():
        subprocess.run(["mkcert", "-cert-file", str(cert), "-key-file", str(key), "localhost", "127.0.0.1", ip,
                        f"{socket.gethostname()}"], check=True)
    print(f"Viewer on the local network: https://{ip}:{args.port}  ({guard}; on the iPad, trust mkcert's root CA"
          f" once, or accept the warning)")
    uvicorn.run(app, host="0.0.0.0", port=args.port, ssl_certfile=str(cert), ssl_keyfile=str(key),
                log_level="warning")
    return 0


def cli() -> None:
    sys.exit(main())
