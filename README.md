# OmniCourse-Lens

Toy dataset and experiments for course-video search.

## Environment

The local development environment is named `omniC` and targets the RTX 5090 with
PyTorch CUDA 13.0 wheels.

Create it from scratch:

```bash
conda env create -f environment.yml
conda activate omniC
python -m ipykernel install --user --name omniC --display-name "Python (omniC)"
```

Verify GPU support:

```bash
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0)); print(torch.cuda.is_available())"
```

## Trials

The first automated moment-retrieval benchmark lives in `Trials/`. It builds a
silver-label benchmark from the paired lecture videos and slides, then reports
Recall@K, MRR, temporal IoU, and timestamp error for retrieval baselines.

```bash
conda activate omniC
python Trials/run_benchmark.py --config Trials/configs/default.yaml
```

The InternVideo3 local web demo supports text-only, image, and video
understanding:

```bash
conda activate omniC
python Trials/demos/internvideo3_web_demo.py --eager-load
```

## Dataset

`Dataset/` contains 9 Introduction to Machine Learning lecture folders. Each folder
keeps one downloaded YouTube lecture video and its matching slide PDF:

- `*_video.mp4`
- `*_slides.pdf`

Sources:

- YouTube playlist: https://www.youtube.com/watch?v=1f0gilKVx2I&list=PLGViarxWrOJcoBMB-iEv153k07o-zkBm8
- Slides: https://github.com/slds-lmu/lecture_i2ml/tree/master/slides-pdf

Do not commit exported YouTube/browser cookies. They are ignored by `.gitignore`.
