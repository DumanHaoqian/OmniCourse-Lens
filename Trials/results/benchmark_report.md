# Moment Retrieval Benchmark Results

Silver labels are generated from slide-image to video-frame alignment with a monotonic slide-order constraint.

## Dataset

- Queries: 81
- Candidate clips: 1900
- Lectures: 9

## Metrics

| model | R@1 | R@5 | R@10 | MRR | top1 IoU | median error (s) | q/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| silver_visual_upper_bound | 1.000 | 1.000 | 1.000 | 1.000 | 0.220 | 0.0 | 13719.3 |
| tfidf_slide_text | 0.926 | 1.000 | 1.000 | 0.955 | 0.182 | 25.0 | 4956.9 |
| clip_text_frame | 0.296 | 0.519 | 0.617 | 0.393 | 0.081 | 75.0 | 6.5 |
| random | 0.012 | 0.037 | 0.099 | 0.044 | 0.020 | 435.0 | 62208.4 |

## Notes

- `silver_visual_upper_bound` is not a deployable text search model; it measures the best possible result if the query were the slide image.
- `tfidf_slide_text` is a strong slide/text-index baseline that maps slide matches back to video moments.
- `clip_text_frame` is the first true multimodal text-to-frame baseline.
- InternVideo3 is scaffolded as an optional generative temporal-grounding trial in `moment_benchmark/internvideo3_adapter.py`.
