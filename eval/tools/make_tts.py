"""Synthetic recording of a case's script with macOS `say`, one voice per speaker (capture dry run).

Clean synthetic speech, not a real room: it tests the pipeline end to end, not capture quality. Recordings of real
role-played meetings are the real test.

    uv run python eval/tools/make_tts.py cases/C01.yaml /tmp/c01-tts.wav
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

VOICES = {"rm": "Daniel", "client": "Samantha", "accountant": "Rishi"}  # en_GB, en_US, en_IN


def main(case_path: str, out: str) -> None:
    case = yaml.safe_load(Path(case_path).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        parts = []
        for i, u in enumerate(case["transcript"]["utterances"], 1):
            f = tmp / f"{i:02d}.aiff"
            subprocess.run(["say", "-v", VOICES.get(u["speaker"], "Samantha"), "-o", str(f), u["text"]], check=True)
            parts.append(f)
        pause = tmp / "pause.aiff"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
                        "-t", "0.6", str(pause)], check=True)
        listing = tmp / "list.txt"
        listing.write_text("".join(f"file '{p}'\nfile '{pause}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-ar", "16000", "-ac", "1", out], check=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
