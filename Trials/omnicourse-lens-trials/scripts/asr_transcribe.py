from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def clip_audio(audio_path: str, max_duration: float | None) -> Path:
    source = Path(audio_path)
    if not source.exists():
        raise FileNotFoundError(audio_path)
    if not max_duration or max_duration <= 0:
        return source
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-t",
        str(max_duration),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(tmp_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if result.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        return source
    return tmp_path


def _run_faster_whisper(args: argparse.Namespace, device: str, compute_type: str) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    started = time.time()
    model = WhisperModel(
        args.model,
        device=device,
        compute_type=compute_type,
        download_root=args.download_root or None,
    )
    segments, info = model.transcribe(
        args.audio_path,
        language=args.language or None,
        task="transcribe",
        beam_size=args.beam_size,
        vad_filter=args.vad_filter,
        condition_on_previous_text=False,
        word_timestamps=args.word_timestamps,
    )
    rows = []
    for segment in segments:
        words = []
        for word in getattr(segment, "words", None) or []:
            words.append(
                {
                    "start_time": float(word.start or 0.0),
                    "end_time": float(word.end or 0.0),
                    "text": str(word.word or "").strip(),
                    "confidence": float(word.probability) if word.probability is not None else None,
                }
            )
        text = str(segment.text or "").strip()
        if not text:
            continue
        rows.append(
            {
                "start_time": round(float(segment.start or 0.0), 3),
                "end_time": round(float(segment.end or 0.0), 3),
                "text": text,
                "confidence": float(segment.avg_logprob) if segment.avg_logprob is not None else None,
                "provider": f"faster_whisper_{args.model}_{device}_{compute_type}",
                "words": words,
            }
        )
    return {
        "provider": "faster_whisper",
        "model": args.model,
        "device": device,
        "compute_type": compute_type,
        "language": getattr(info, "language", args.language),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "elapsed": round(time.time() - started, 2),
        "segments": rows,
    }


def faster_whisper_transcribe(args: argparse.Namespace) -> dict[str, Any]:
    candidates = [(args.device, args.compute_type)]
    if args.device == "cuda":
        candidates.append(("cpu", "int8"))
    elif args.device == "auto":
        candidates = [("cuda", args.compute_type), ("cpu", "int8")]
    errors = []
    for device, compute_type in candidates:
        try:
            payload = _run_faster_whisper(args, device, compute_type)
            if errors:
                payload["fallback_errors"] = errors
            return payload
        except Exception as exc:
            errors.append({"device": device, "compute_type": compute_type, "error": type(exc).__name__, "message": str(exc)[:500]})
    raise RuntimeError(f"faster-whisper failed on all devices: {errors}")


def openai_whisper_transcribe(args: argparse.Namespace) -> dict[str, Any]:
    import torch
    import whisper

    started = time.time()
    device = "cuda" if args.device in {"auto", "cuda"} and torch.cuda.is_available() else "cpu"
    model = whisper.load_model(args.model, device=device, download_root=args.download_root or None)
    result = model.transcribe(
        args.audio_path,
        language=args.language or None,
        task="transcribe",
        fp16=device == "cuda",
        condition_on_previous_text=False,
        word_timestamps=args.word_timestamps,
    )
    rows = []
    for segment in result.get("segments", []):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        rows.append(
            {
                "start_time": round(float(segment.get("start", 0.0)), 3),
                "end_time": round(float(segment.get("end", 0.0)), 3),
                "text": text,
                "confidence": None,
                "provider": f"openai_whisper_{args.model}_{device}",
                "words": [
                    {
                        "start_time": float(word.get("start", 0.0)),
                        "end_time": float(word.get("end", 0.0)),
                        "text": str(word.get("word", "")).strip(),
                        "confidence": float(word.get("probability")) if word.get("probability") is not None else None,
                    }
                    for word in segment.get("words", [])
                ],
            }
        )
    return {
        "provider": "openai_whisper",
        "model": args.model,
        "device": device,
        "language": result.get("language"),
        "elapsed": round(time.time() - started, 2),
        "segments": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio-path", required=True)
    parser.add_argument("--provider", default="faster_whisper", choices=["faster_whisper", "openai_whisper"])
    parser.add_argument("--model", default="small.en")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--language", default="en")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--vad-filter", action="store_true")
    parser.add_argument("--word-timestamps", action="store_true")
    parser.add_argument("--download-root", default="")
    parser.add_argument("--max-duration", type=float, default=0.0)
    args = parser.parse_args()

    original_audio = args.audio_path
    clipped = clip_audio(original_audio, args.max_duration)
    args.audio_path = str(clipped)
    try:
        if args.provider == "faster_whisper":
            payload = faster_whisper_transcribe(args)
        else:
            payload = openai_whisper_transcribe(args)
        payload["source_audio"] = original_audio
        payload["transcribed_audio"] = str(clipped)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"provider": args.provider, "segments": [], "error": type(exc).__name__, "message": str(exc)[:1000]}, ensure_ascii=False))
        return 1
    finally:
        if clipped != Path(original_audio):
            clipped.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
