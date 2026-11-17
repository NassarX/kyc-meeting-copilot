"""Does Whisper invent words in long gaps?

Builds synthetic speech for a case script with macOS `say`, inserts four 30 s gaps (digital silence, quiet pink, loud
brown, faint white noise), and makes a second copy with room noise throughout. Transcribes both locally with Whisper,
with today's settings and with `hallucination_silence_threshold`, then reports words inside the gaps, script recall,
and how well a segment's mean word probability separates invented segments from real ones. No API calls.

    uv run --extra audio python eval/tools/gap_probe.py build cases/C01.yaml OUT/C01
    uv run --extra audio python eval/tools/gap_probe.py run OUT/C01
    uv run python eval/tools/gap_probe.py summarize OUT          # every OUT/<case> that has been run

Noise uses fixed seeds, so a rebuild gives the same audio; Whisper on it is deterministic at temperature 0, but
results can still differ from earlier unseeded runs. Use a case-unique folder name per case: macOS file names
ignore case, so `c01` and `C01` are the same folder.
"""
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

VOICES = {"rm": "Daniel", "client": "Samantha", "accountant": "Rishi"}
SR = 16000
GAP_S = 30.0
GAPS = {3: ("silence", "anullsrc=r=16000:cl=mono"),  # inserted after these utterances (1-based)
        6: ("room", "anoisesrc=color=pink:amplitude=0.02:r=16000:seed=6"),
        9: ("loud", "anoisesrc=color=brown:amplitude=0.2:r=16000:seed=9"),
        12: ("room2", "anoisesrc=color=white:amplitude=0.01:r=16000:seed=12")}
SETTINGS = {"current": {"condition_on_previous_text": False},
            "hst2": {"condition_on_previous_text": False, "hallucination_silence_threshold": 2.0}}
AUDIO = ("gapped", "gapped-noisy")
THRESHOLDS = (0.6, 0.7, 0.75, 0.8)


def _ff(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def _duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out)


def build(case_path: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    utts = yaml.safe_load(case_path.read_text(encoding="utf-8"))["transcript"]["utterances"]
    pause = out / "pause.wav"
    _ff("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.6", str(pause))
    parts, t, gaps = [], 0.0, []
    for i, u in enumerate(utts, 1):
        aiff, wav = out / f"u{i:02d}.aiff", out / f"u{i:02d}.wav"
        subprocess.run(["say", "-v", VOICES.get(u["speaker"], "Samantha"), "-o", str(aiff), u["text"]], check=True)
        _ff("-i", str(aiff), "-ar", str(SR), "-ac", "1", str(wav))
        parts += [wav, pause]
        t += _duration(wav) + 0.6
        if i in GAPS:
            kind, src = GAPS[i]
            gap = out / f"gap-{kind}.wav"
            _ff("-f", "lavfi", "-i", src, "-t", str(GAP_S), "-ar", str(SR), "-ac", "1", str(gap))
            gaps.append({"kind": kind, "start": t, "end": t + GAP_S})
            parts.append(gap)
            t += GAP_S
    listing = out / "list.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    _ff("-f", "concat", "-safe", "0", "-i", str(listing), "-ar", str(SR), "-ac", "1", str(out / "gapped.wav"))
    _ff("-i", str(out / "gapped.wav"), "-filter_complex",
        "anoisesrc=color=pink:amplitude=0.05:r=16000:seed=1[n];[0][n]amix=inputs=2:duration=first:weights=1 1",
        str(out / "gapped-noisy.wav"))
    meta = {"case": case_path.stem, "gaps": gaps, "script": " ".join(u["text"] for u in utts)}
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    print(f"{case_path.stem}: {t:.0f} s, gaps at {[round(g['start']) for g in gaps]}")


def run(out: Path) -> None:
    import mlx_whisper
    for audio in AUDIO:
        for name, opts in SETTINGS.items():
            r = mlx_whisper.transcribe(str(out / f"{audio}.wav"), path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
                                       language="en", word_timestamps=True, **opts)
            segs = [{"start": s["start"], "end": s["end"], "text": s["text"],
                     "words": [{k: w[k] for k in ("word", "start", "end", "probability")} for w in s.get("words", [])]}
                    for s in r["segments"]]
            (out / f"tx-{audio}-{name}.json").write_text(json.dumps(segs))
            print(f"{out.name} {audio} {name}: {len(segs)} segments")


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def _in_gap(w: dict, gaps: list[dict]) -> bool:
    mid = (w["start"] + w["end"]) / 2
    return any(g["start"] + 0.3 < mid < g["end"] - 0.3 for g in gaps)


def summarize(root: Path) -> None:
    rows, invented, real = [], [], []
    for d in sorted(p for p in root.iterdir() if (p / "meta.json").exists()):
        meta = json.loads((d / "meta.json").read_text())
        ref = [_norm(w) for w in meta["script"].split() if _norm(w)]
        for audio in AUDIO:
            for name in SETTINGS:
                f = d / f"tx-{audio}-{name}.json"
                if not f.exists():
                    continue
                segs = json.loads(f.read_text())
                words = [w for s in segs for w in s["words"]]
                hyp = [_norm(w["word"]) for w in words if _norm(w["word"])]
                sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
                gap_words = [w["word"].strip() for w in words if _in_gap(w, meta["gaps"])]
                rows.append((meta.get("case", d.name), audio, name, len(gap_words),
                             sum(b.size for b in sm.get_matching_blocks()) / len(ref), " ".join(gap_words)[:70]))
                if name != "current":
                    continue
                for s in segs:
                    ws = s["words"]
                    if ws:
                        mean = sum(w["probability"] for w in ws) / len(ws)
                        lowest = min(w["probability"] for w in ws)
                        in_gap = sum(_in_gap(w, meta["gaps"]) for w in ws) >= len(ws) / 2
                        (invented if in_gap else real).append((mean, lowest, meta.get("case", d.name), s["text"].strip()))
    print("| Case | Audio | Setting | Words in gaps | Script recall | Gap text |\n|---|---|---|---|---|---|")
    for c, a, n, g, rec, txt in rows:
        print(f"| {c} | {a} | {n} | {g} | {rec:.3f} | {txt} |")
    for name in SETTINGS:
        for audio in AUDIO:
            sel = [r for r in rows if r[1] == audio and r[2] == name]
            if sel:
                print(f"\n{name} / {audio}: words in gaps {sum(r[3] for r in sel)}, cases with any "
                      f"{sum(r[3] > 0 for r in sel)}/{len(sel)}, mean script recall {sum(r[4] for r in sel) / len(sel):.3f}")
    print(f"\nSegments under today's settings: {len(invented)} invented (mostly inside a gap), {len(real)} real.")
    for t in THRESHOLDS:
        print(f"- mean word probability < {t}: catches {sum(m < t for m, *_ in invented)}/{len(invented)} invented, "
              f"flags {sum(m < t for m, *_ in real)}/{len(real)} real")
    print(f"- any word < 0.5 (the existing rule): catches {sum(lo < 0.5 for _, lo, *_ in invented)}/{len(invented)} "
          f"invented, touches {sum(lo < 0.5 for _, lo, *_ in real)}/{len(real)} real")
    print("\nInvented segments:")
    for m, lo, c, txt in invented:
        print(f"- {c}: \"{txt}\" (mean {m:.2f}, lowest word {lo:.2f})")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "build":
        build(Path(sys.argv[2]), Path(sys.argv[3]))
    elif cmd == "run":
        run(Path(sys.argv[2]))
    else:
        summarize(Path(sys.argv[2]))
