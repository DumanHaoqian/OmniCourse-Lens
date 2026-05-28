from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def encode_texts(texts: list[str], model_name: str, cache_dir: str | None, batch_size: int) -> dict[str, Any]:
    from sentence_transformers import SentenceTransformer

    started = time.time()
    model = SentenceTransformer(model_name, cache_folder=cache_dir or None)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return {
        "provider": "sentence_transformers",
        "model": model_name,
        "dimension": int(embeddings.shape[1]) if len(embeddings.shape) == 2 else 0,
        "count": int(embeddings.shape[0]) if len(embeddings.shape) else 0,
        "elapsed": round(time.time() - started, 2),
        "embeddings": embeddings.round(6).tolist(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", help="JSON file with a list of texts.")
    parser.add_argument("--text", help="Single text to encode.")
    parser.add_argument("--output-json", help="Where to write embeddings JSON. Defaults to stdout.")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--cache-dir", default="")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    if args.input_json:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        texts = payload if isinstance(payload, list) else payload.get("texts", [])
    elif args.text is not None:
        texts = [args.text]
    else:
        raise SystemExit("--input-json or --text is required")

    result = encode_texts([str(text or "") for text in texts], args.model, args.cache_dir, args.batch_size)
    output = json.dumps(result, ensure_ascii=False)
    if args.output_json:
        Path(args.output_json).write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
