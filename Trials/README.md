# Trials

This directory contains model and algorithm trials for course-video moment
retrieval. The first benchmark is intentionally small and automatic: it turns the
existing lecture videos plus slide PDFs into a silver-label retrieval benchmark.

## Benchmark Design

Because the dataset does not yet have human moment annotations, the benchmark
creates silver labels by:

1. Rendering each slide page to an image and extracting its text.
2. Sampling frames from each corresponding lecture video.
3. Matching slide images to video frames with a lightweight visual signature.
4. Treating the matched timestamp as the target moment for that slide-text query.

The main metrics are:

- `recall@k`: whether a relevant moment appears in the top `k` results.
- `mrr`: reciprocal rank of the first relevant result.
- `top1_iou`: temporal IoU between the top result and the silver window.
- `median_abs_error_sec`: timestamp error of the top result.
- `queries_per_second`: rough retrieval throughput.

## Run

```bash
conda activate omniC
python Trials/run_benchmark.py --config Trials/configs/default.yaml
```

The default run evaluates:

- `random`: sanity-check lower bound.
- `silver_visual_upper_bound`: slide-image to frame matching upper bound.
- `tfidf_slide_text`: text-only slide index baseline mapped back to video time.
- `clip_text_frame`: CLIP text-to-video-frame retrieval baseline.

InternVideo3 is included as an optional generative temporal-grounding adapter in
`moment_benchmark/internvideo3_adapter.py`. It is not part of the default run
because the reachable Hugging Face checkpoint is roughly 18.7 GB and generation
over all benchmark queries is expensive. Use it on a small query subset first.

## InternVideo3 Web Demo

The local checkpoint should live at:

```text
Trials/checkpoints/InternVideo3-8B-Instruct
```

Run the Gradio demo:

```bash
conda activate omniC
python Trials/demos/internvideo3_web_demo.py --eager-load
```

The demo supports text-only conversation, image understanding, and video
understanding against either an uploaded video or one of the videos in
`Dataset/`.
