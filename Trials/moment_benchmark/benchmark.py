from __future__ import annotations

import argparse
import json
import math
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import fitz
import numpy as np
import torch
import yaml
from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from transformers import CLIPModel, CLIPProcessor


@dataclass(frozen=True)
class Lecture:
    lecture_id: str
    title: str
    folder: Path
    video_path: Path
    slides_path: Path
    duration_sec: float


@dataclass(frozen=True)
class Query:
    query_id: str
    lecture_id: str
    slide_index: int
    text: str
    label_start_sec: float
    label_end_sec: float
    label_center_sec: float
    silver_score: float


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    lecture_id: str
    center_sec: float
    start_sec: float
    end_sec: float
    frame_rgb: np.ndarray


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()
    return text


def title_from_lecture_id(lecture_id: str) -> str:
    parts = lecture_id.split("_", 1)
    title = parts[1] if len(parts) == 2 else lecture_id
    return title.replace("_", " ")


def video_duration_sec(path: Path) -> float:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    if not fps or not frames:
        raise RuntimeError(f"Could not read duration for {path}")
    return float(frames / fps)


def discover_lectures(dataset_dir: Path) -> list[Lecture]:
    lectures: list[Lecture] = []
    for folder in sorted(p for p in dataset_dir.iterdir() if p.is_dir()):
        videos = sorted(folder.glob("*__video.mp4"))
        slides = sorted(folder.glob("*__slides.pdf"))
        if len(videos) != 1 or len(slides) != 1:
            raise RuntimeError(f"Expected one video and one slides PDF in {folder}")
        lecture_id = folder.name
        lectures.append(
            Lecture(
                lecture_id=lecture_id,
                title=title_from_lecture_id(lecture_id),
                folder=folder,
                video_path=videos[0],
                slides_path=slides[0],
                duration_sec=video_duration_sec(videos[0]),
            )
        )
    return lectures


def render_slide_page(page: fitz.Page, zoom: float) -> Image.Image:
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def image_signature(image: Image.Image | np.ndarray) -> np.ndarray:
    if isinstance(image, Image.Image):
        rgb = np.asarray(image.convert("RGB"))
    else:
        rgb = image
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray_small = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA).astype(np.float32)
    gray_small = (gray_small - gray_small.mean()) / (gray_small.std() + 1e-6)
    edges = cv2.Canny(gray, 80, 160)
    edges_small = cv2.resize(edges, (160, 90), interpolation=cv2.INTER_AREA).astype(np.float32)
    edges_small = (edges_small - edges_small.mean()) / (edges_small.std() + 1e-6)
    feature = np.concatenate([gray_small.reshape(-1), 0.5 * edges_small.reshape(-1)])
    feature = feature / (np.linalg.norm(feature) + 1e-8)
    return feature.astype(np.float32)


def sample_video_candidates(lecture: Lecture, interval_sec: float, clip_duration_sec: float) -> list[Candidate]:
    cap = cv2.VideoCapture(str(lecture.video_path))
    candidates: list[Candidate] = []
    half = clip_duration_sec / 2.0
    times = np.arange(0.0, lecture.duration_sec, interval_sec)
    for idx, center in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_MSEC, float(center * 1000.0))
        ok, frame_bgr = cap.read()
        if not ok:
            continue
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        candidates.append(
            Candidate(
                candidate_id=f"{lecture.lecture_id}::frame_{idx:05d}",
                lecture_id=lecture.lecture_id,
                center_sec=float(center),
                start_sec=max(0.0, float(center - half)),
                end_sec=min(lecture.duration_sec, float(center + half)),
                frame_rgb=frame_rgb,
            )
        )
    cap.release()
    return candidates


def load_slide_texts_and_signatures(lecture: Lecture, render_zoom: float) -> tuple[list[str], np.ndarray]:
    doc = fitz.open(lecture.slides_path)
    texts: list[str] = []
    signatures: list[np.ndarray] = []
    for page in doc:
        text = clean_text(page.get_text("text"))
        texts.append(text)
        signatures.append(image_signature(render_slide_page(page, render_zoom)))
    return texts, np.stack(signatures)


def monotonic_match(
    score_matrix: np.ndarray,
    duration_sec: float,
    candidate_centers: np.ndarray,
    prior_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    n_slides, n_candidates = score_matrix.shape
    adjusted = score_matrix.copy()
    if prior_weight:
        for i in range(n_slides):
            expected = duration_sec * (i + 0.5) / max(n_slides, 1)
            scale = max(duration_sec / max(n_slides, 1), 1.0)
            adjusted[i] += prior_weight * np.exp(-np.abs(candidate_centers - expected) / scale)

    dp = np.full((n_slides, n_candidates), -np.inf, dtype=np.float32)
    back = np.zeros((n_slides, n_candidates), dtype=np.int32)
    dp[0] = adjusted[0]
    for i in range(1, n_slides):
        best_prev = -np.inf
        best_idx = 0
        for j in range(n_candidates):
            if dp[i - 1, j] > best_prev:
                best_prev = dp[i - 1, j]
                best_idx = j
            dp[i, j] = adjusted[i, j] + best_prev
            back[i, j] = best_idx

    chosen = np.zeros(n_slides, dtype=np.int32)
    chosen[-1] = int(np.argmax(dp[-1]))
    for i in range(n_slides - 1, 0, -1):
        chosen[i - 1] = back[i, chosen[i]]
    return chosen, score_matrix[np.arange(n_slides), chosen]


def build_benchmark(config: dict[str, Any]) -> tuple[list[Lecture], list[Query], list[Candidate], dict[str, Any]]:
    dataset_dir = Path(config["dataset_dir"])
    sampling = config["sampling"]
    silver_cfg = config["silver_labels"]
    lectures = discover_lectures(dataset_dir)
    all_queries: list[Query] = []
    all_candidates: list[Candidate] = []
    build_meta: dict[str, Any] = {"lectures": []}

    for lecture in lectures:
        candidates = sample_video_candidates(
            lecture,
            interval_sec=float(sampling["frame_interval_sec"]),
            clip_duration_sec=float(sampling["clip_duration_sec"]),
        )
        frame_signatures = np.stack([image_signature(c.frame_rgb) for c in candidates])
        slide_texts, slide_signatures = load_slide_texts_and_signatures(
            lecture, render_zoom=float(silver_cfg["render_zoom"])
        )
        score_matrix = slide_signatures @ frame_signatures.T
        centers = np.array([c.center_sec for c in candidates], dtype=np.float32)
        chosen, silver_scores = monotonic_match(
            score_matrix,
            duration_sec=lecture.duration_sec,
            candidate_centers=centers,
            prior_weight=float(silver_cfg["monotonic_time_prior_weight"]),
        )
        matched_centers = centers[chosen]
        min_window = float(silver_cfg["min_window_sec"])

        for slide_index, center in enumerate(matched_centers):
            prev_center = matched_centers[slide_index - 1] if slide_index > 0 else 0.0
            next_center = (
                matched_centers[slide_index + 1]
                if slide_index + 1 < len(matched_centers)
                else lecture.duration_sec
            )
            start = min(center, max(0.0, (prev_center + center) / 2.0))
            end = max(center, min(lecture.duration_sec, (center + next_center) / 2.0))
            if end - start < min_window:
                start = max(0.0, center - min_window / 2.0)
                end = min(lecture.duration_sec, center + min_window / 2.0)
            text = clean_text(slide_texts[slide_index])
            all_queries.append(
                Query(
                    query_id=f"{lecture.lecture_id}::slide_{slide_index + 1:03d}",
                    lecture_id=lecture.lecture_id,
                    slide_index=slide_index,
                    text=text,
                    label_start_sec=float(start),
                    label_end_sec=float(end),
                    label_center_sec=float(center),
                    silver_score=float(silver_scores[slide_index]),
                )
            )

        all_candidates.extend(candidates)
        build_meta["lectures"].append(
            {
                "lecture_id": lecture.lecture_id,
                "duration_sec": lecture.duration_sec,
                "slides": len(slide_texts),
                "candidates": len(candidates),
                "mean_silver_score": float(np.mean(silver_scores)),
            }
        )

    min_chars = int(sampling.get("min_query_chars") or 0)
    queries = [q for q in all_queries if len(q.text) >= min_chars]
    max_queries = sampling.get("max_queries")
    if max_queries:
        queries = queries[: int(max_queries)]
    build_meta["total_queries_before_filter"] = len(all_queries)
    build_meta["total_queries"] = len(queries)
    build_meta["total_candidates"] = len(all_candidates)
    return lectures, queries, all_candidates, build_meta


def iou(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    inter = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    union = max(a_end, b_end) - min(a_start, b_start)
    return inter / union if union > 0 else 0.0


def relevant(query: Query, candidate: Candidate) -> bool:
    center_hit = query.label_start_sec <= candidate.center_sec <= query.label_end_sec
    overlap_hit = iou(query.label_start_sec, query.label_end_sec, candidate.start_sec, candidate.end_sec) > 0.1
    return query.lecture_id == candidate.lecture_id and (center_hit or overlap_hit)


def evaluate_scores(
    model_name: str,
    scores: np.ndarray,
    queries: list[Query],
    candidates: list[Candidate],
    elapsed_sec: float,
) -> dict[str, Any]:
    ranks: list[int | None] = []
    top1_ious: list[float] = []
    top1_errors: list[float] = []
    for qi, query in enumerate(queries):
        order = np.argsort(-scores[qi])
        first_rank: int | None = None
        for rank, ci in enumerate(order, start=1):
            if relevant(query, candidates[int(ci)]):
                first_rank = rank
                break
        ranks.append(first_rank)
        top = candidates[int(order[0])]
        top1_ious.append(iou(query.label_start_sec, query.label_end_sec, top.start_sec, top.end_sec))
        top1_errors.append(abs(top.center_sec - query.label_center_sec))

    def recall_at(k: int) -> float:
        return float(np.mean([rank is not None and rank <= k for rank in ranks]))

    reciprocal = [0.0 if rank is None else 1.0 / rank for rank in ranks]
    return {
        "model": model_name,
        "queries": len(queries),
        "candidates": len(candidates),
        "recall@1": recall_at(1),
        "recall@5": recall_at(5),
        "recall@10": recall_at(10),
        "mrr": float(np.mean(reciprocal)),
        "top1_iou": float(np.mean(top1_ious)),
        "median_abs_error_sec": float(np.median(top1_errors)),
        "mean_abs_error_sec": float(np.mean(top1_errors)),
        "elapsed_sec": float(elapsed_sec),
        "queries_per_second": float(len(queries) / elapsed_sec) if elapsed_sec > 0 else math.inf,
    }


def score_random(queries: list[Query], candidates: list[Candidate]) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.normal(size=(len(queries), len(candidates))).astype(np.float32)


def score_silver_visual_upper_bound(queries: list[Query], candidates: list[Candidate]) -> np.ndarray:
    scores = np.full((len(queries), len(candidates)), -1e6, dtype=np.float32)
    for qi, q in enumerate(queries):
        for ci, c in enumerate(candidates):
            if c.lecture_id != q.lecture_id:
                continue
            scores[qi, ci] = -abs(c.center_sec - q.label_center_sec)
    return scores


def score_tfidf_slide_text(queries: list[Query], candidates: list[Candidate]) -> np.ndarray:
    slide_docs = [q.text for q in queries]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=12000)
    slide_matrix = vectorizer.fit_transform(slide_docs)
    query_matrix = vectorizer.transform([q.text for q in queries])
    slide_similarity = (query_matrix @ slide_matrix.T).toarray().astype(np.float32)

    candidate_to_slide = []
    for c in candidates:
        best_idx = 0
        best_error = float("inf")
        for qi, q in enumerate(queries):
            if q.lecture_id != c.lecture_id:
                continue
            err = abs(c.center_sec - q.label_center_sec)
            if err < best_error:
                best_error = err
                best_idx = qi
        candidate_to_slide.append(best_idx)
    return slide_similarity[:, candidate_to_slide]


def batched(iterable: list[Any], batch_size: int):
    for i in range(0, len(iterable), batch_size):
        yield iterable[i : i + batch_size]


def l2_normalize(x: np.ndarray) -> np.ndarray:
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-8)


def pooled_tensor(output: Any) -> torch.Tensor:
    if isinstance(output, torch.Tensor):
        return output
    if hasattr(output, "pooler_output") and output.pooler_output is not None:
        return output.pooler_output
    if hasattr(output, "image_embeds") and output.image_embeds is not None:
        return output.image_embeds
    if hasattr(output, "text_embeds") and output.text_embeds is not None:
        return output.text_embeds
    raise TypeError(f"Unsupported CLIP feature output: {type(output)!r}")


def score_clip_text_frame(
    queries: list[Query],
    candidates: list[Candidate],
    model_name: str,
    batch_size: int,
) -> np.ndarray:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CLIPModel.from_pretrained(model_name).to(device)
    processor = CLIPProcessor.from_pretrained(model_name)
    model.eval()

    text_features: list[np.ndarray] = []
    with torch.inference_mode():
        for batch in batched([q.text[:900] for q in queries], batch_size):
            inputs = processor(text=batch, return_tensors="pt", padding=True, truncation=True).to(device)
            feats = pooled_tensor(model.get_text_features(**inputs))
            text_features.append(feats.float().cpu().numpy())
    text_matrix = l2_normalize(np.concatenate(text_features, axis=0))

    image_features: list[np.ndarray] = []
    images = [Image.fromarray(c.frame_rgb) for c in candidates]
    with torch.inference_mode():
        for batch in batched(images, batch_size):
            inputs = processor(images=batch, return_tensors="pt").to(device)
            feats = pooled_tensor(model.get_image_features(**inputs))
            image_features.append(feats.float().cpu().numpy())
    image_matrix = l2_normalize(np.concatenate(image_features, axis=0))
    return (text_matrix @ image_matrix.T).astype(np.float32)


def write_report(
    output_dir: Path,
    config: dict[str, Any],
    build_meta: dict[str, Any],
    metrics: list[dict[str, Any]],
    queries: list[Query],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "config": config,
        "benchmark": build_meta,
        "metrics": metrics,
        "query_examples": [
            {
                "query_id": q.query_id,
                "text": q.text[:220],
                "label": [q.label_start_sec, q.label_end_sec],
                "silver_score": q.silver_score,
            }
            for q in queries[:8]
        ],
    }
    (output_dir / "benchmark_results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Moment Retrieval Benchmark Results",
        "",
        "Silver labels are generated from slide-image to video-frame alignment with a monotonic slide-order constraint.",
        "",
        "## Dataset",
        "",
        f"- Queries: {build_meta['total_queries']}",
        f"- Candidate clips: {build_meta['total_candidates']}",
        f"- Lectures: {len(build_meta['lectures'])}",
        "",
        "## Metrics",
        "",
        "| model | R@1 | R@5 | R@10 | MRR | top1 IoU | median error (s) | q/s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(metrics, key=lambda r: r["mrr"], reverse=True):
        lines.append(
            "| {model} | {r1:.3f} | {r5:.3f} | {r10:.3f} | {mrr:.3f} | {iou:.3f} | {err:.1f} | {qps:.1f} |".format(
                model=row["model"],
                r1=row["recall@1"],
                r5=row["recall@5"],
                r10=row["recall@10"],
                mrr=row["mrr"],
                iou=row["top1_iou"],
                err=row["median_abs_error_sec"],
                qps=row["queries_per_second"],
            )
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `silver_visual_upper_bound` is not a deployable text search model; it measures the best possible result if the query were the slide image.",
            "- `tfidf_slide_text` is a strong slide/text-index baseline that maps slide matches back to video moments.",
            "- `clip_text_frame` is the first true multimodal text-to-frame baseline.",
            "- InternVideo3 is scaffolded as an optional generative temporal-grounding trial in `moment_benchmark/internvideo3_adapter.py`.",
        ]
    )
    (output_dir / "benchmark_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config_path: Path) -> None:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    output_dir = Path(config["output_dir"])
    random.seed(42)
    np.random.seed(42)
    lectures, queries, candidates, build_meta = build_benchmark(config)
    del lectures

    metrics: list[dict[str, Any]] = []
    for model_name in config["models"]:
        start = time.perf_counter()
        if model_name == "random":
            scores = score_random(queries, candidates)
        elif model_name == "silver_visual_upper_bound":
            scores = score_silver_visual_upper_bound(queries, candidates)
        elif model_name == "tfidf_slide_text":
            scores = score_tfidf_slide_text(queries, candidates)
        elif model_name == "clip_text_frame":
            scores = score_clip_text_frame(
                queries,
                candidates,
                model_name=config["clip"]["model_name"],
                batch_size=int(config["clip"]["batch_size"]),
            )
        else:
            raise ValueError(f"Unknown model: {model_name}")
        elapsed = time.perf_counter() - start
        row = evaluate_scores(model_name, scores, queries, candidates, elapsed)
        metrics.append(row)
        print(json.dumps(row, indent=2), flush=True)

    write_report(output_dir, config, build_meta, metrics, queries)
    print(f"Wrote {output_dir / 'benchmark_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
