"""Read back local narration without sending audio to an external service."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata

import librosa
import numpy as np
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parents[3]


def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    for raw, replacement in (("十八点九", "18.9"), ("18・9", "18.9"),
                             ("三十", "30"), ("メートル", "m"), ("繋", "つな")):
        text = text.replace(raw, replacement)
    # Keep decimal points; discard sentence punctuation and spacing.
    return re.sub(r"[^\w.]|(?<!\d)\.|\.(?!\d)", "", text)


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        nxt = [i]
        for j, y in enumerate(b, 1):
            nxt.append(min(nxt[-1]+1, row[j]+1, row[j-1]+(x != y)))
        row = nxt
    return row[-1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("records", type=Path, nargs="+")
    args = p.parse_args()
    model = WhisperModel(str(args.model.resolve()), device="cpu", compute_type="int8",
                         cpu_threads=8, local_files_only=True)
    checked = []
    for record_path in args.records:
        records = json.loads(record_path.read_text(encoding="utf-8"))
        for row in records:
            path = ROOT / row["path"]
            if sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"Take changed: {path}")
            parts, _ = model.transcribe(str(path), language="ja", beam_size=5,
                                       temperature=0, condition_on_previous_text=False)
            parts = list(parts)
            text = "".join(s.text for s in parts)
            recognized, reference = normalize(text), normalize(row["text"])
            signal, sr = librosa.load(str(path), sr=16_000)
            f0, voiced, _ = librosa.pyin(signal, fmin=65, fmax=390, sr=sr,
                                        frame_length=1024, hop_length=256)
            pitches = f0[voiced & np.isfinite(f0)]
            critical = [term for term in ("18.9m", "30m", "未達", "移行予定") if term in reference]
            checked.append(dict(candidate=row["candidate"], case=row["case"],
                duration_s=row["duration_s"], synthesis_s=row["synthesis_s"], rtf=row["rtf"],
                asr_text=text, normalized_cer=round(distance(reference, recognized)/max(1, len(reference)), 4),
                critical_terms_read_back={term:term in recognized for term in critical},
                pitch_median_hz=round(float(np.median(pitches)), 1) if len(pitches) else None,
                pitch_p10_p90_hz=[round(float(v), 1) for v in np.percentile(pitches, [10, 90])] if len(pitches) else None,
                segments=[dict(start_s=s.start, end_s=s.end, text=s.text) for s in parts],
                wav_path=row["path"], wav_sha256=row["sha256"]))
            print(row["candidate"], row["case"], checked[-1]["normalized_cer"], text, flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = dict(review="automatic_only", asr="Systran/faster-whisper-small",
                  pitch="librosa.pyin (estimated)", records=checked)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
