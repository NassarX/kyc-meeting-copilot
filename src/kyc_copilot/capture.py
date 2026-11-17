"""Audio to transcript, locally (capture test).

mlx-whisper on Apple Silicon: the audio never leaves the machine. Whisper gives text segments, not speakers, so every
utterance is labelled `unknown`; the extractor is told to infer roles from context. Transcripts are cached by the
audio's SHA-256 and the model, so a re-run costs nothing.

Install the optional extra first: `uv sync --extra audio`.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path

from kyc_copilot.eval.case_format import Transcript, Utterance, WordScore

DEFAULT_ASR = "mlx-community/whisper-large-v3-turbo"
UNKNOWN = "unknown"
ASR_FORMAT = "words-v1"  # cache key part: transcripts now keep per-word probabilities and timings
UNCLEAR = 0.5  # a word the transcriber gave less than this is flagged (clean audio had none below it)
UNSURE_SEGMENT = 0.7  # a segment averaging less than this may be invented: all 7 gap inventions, 10 of 498 real
_NO_BREAK = {"Mr", "Ms", "Mrs", "Dr", "Prof", "St", "Mt", "Inc", "Ltd", "Co", "No", "vs"}
CACHE_DIR = Path(__file__).parents[2] / ".eval-cache"


def _word_scores(text: str, raw: str, words: list[dict]) -> tuple[WordScore, ...]:
    """Place each transcribed word in the stripped utterance text by walking forward through it."""
    out, pos = [], 0
    for w in words:
        token = w.get("word", "").strip()
        if not token:
            continue
        i = text.find(token, pos)
        if i < 0:
            continue
        out.append(WordScore(start=i, end=i + len(token), probability=min(max(float(w.get("probability", 1.0)), 0.0), 1.0),
                             t_start=float(w.get("start", 0.0)), t_end=float(w.get("end", 0.0))))
        pos = i + len(token)
    return tuple(out)


def segments_to_transcript(segments: list[dict], meeting_date: date) -> Transcript:
    utts = []
    for s in segments:
        text = s.get("text", "").strip()
        if text:
            utts.append(Utterance(utt_id=f"u-{len(utts) + 1:02d}", speaker=UNKNOWN, text=text,
                                  words=_word_scores(text, s["text"], s.get("words", []))))
    return Transcript(meeting_date=meeting_date, utterances=tuple(utts))


def _whisper(path: str, model: str) -> list[dict]:
    try:
        import mlx_whisper
    except ImportError as e:  # pragma: no cover - depends on the optional extra
        raise RuntimeError("audio needs the optional extra: cd poc && uv sync --extra audio") from e
    result = mlx_whisper.transcribe(path, path_or_hf_repo=model, language="en", condition_on_previous_text=False,
                                    word_timestamps=True)
    return [{"start": s["start"], "end": s["end"], "text": s["text"],
             "words": [{"word": w["word"], "start": w["start"], "end": w["end"], "probability": w["probability"]}
                       for w in s.get("words", [])]} for s in result["segments"]]


def transcribe(audio: Path, meeting_date: date, model: str = DEFAULT_ASR, use_cache: bool = True,
               engine: Callable[[str, str], list[dict]] = _whisper) -> Transcript:
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    path = CACHE_DIR / f"asr-{hashlib.sha256((digest + model + ASR_FORMAT).encode()).hexdigest()[:32]}.json"
    if use_cache and path.exists():
        segments = json.loads(path.read_text(encoding="utf-8"))["segments"]
    else:
        segments = engine(str(audio), model)
        if use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": model, "audio_sha256": digest, "segments": segments}),
                            encoding="utf-8")
    return segments_to_transcript(segments, meeting_date)


def read_device_transcript(path: Path, meeting_date: date) -> Transcript:
    """A transcript copied out of a device app (Voice Memos, Notes): plain text with no speaker labels. Split into
    sentences so quotes stay short; never guess speakers."""
    text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).strip()
    sentences, start = [], 0
    for m in re.finditer(r"[.!?]\s+(?=[A-Z0-9\"'])", text):
        before = text[start:m.start() + 1].split()[-1] if text[start:m.start() + 1].split() else ""
        if before.rstrip(".") in _NO_BREAK or re.fullmatch(r"(?:[A-Z]\.){1,3}", before):  # Dr., Ms., S.A.
            continue
        sentences.append(text[start:m.start() + 1].strip())
        start = m.end()
    sentences = [s for s in sentences + [text[start:].strip()] if s]
    if not sentences:
        raise ValueError(f"{path}: empty transcript")
    return Transcript(meeting_date=meeting_date, utterances=tuple(
        Utterance(utt_id=f"u-{i:02d}", speaker=UNKNOWN, text=t) for i, t in enumerate(sentences, 1)))


def unclear_words(utt: Utterance, start: int, end: int) -> list[WordScore]:
    """Words under a quote that the transcriber was unsure of."""
    return [w for w in utt.words if w.start < end and w.end > start and w.probability < UNCLEAR]


def unsure_segment(utt: Utterance) -> float | None:
    """The segment's mean word probability, when it is low enough that Whisper may have invented the segment."""
    if not utt.words:
        return None
    mean = sum(w.probability for w in utt.words) / len(utt.words)
    return mean if mean < UNSURE_SEGMENT else None
