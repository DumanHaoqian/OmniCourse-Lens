from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import ensure_directories, settings  # noqa: E402
from app.schemas import ASRSegment, Course, FormulaBlock, Lecture, Moment, OCRBlock  # noqa: E402
from app.storage import save_course, static_url  # noqa: E402


COURSE_ID = "ml_foundations"


LECTURES = [
    {
        "lecture_id": "lec_01",
        "title": "Linear Regression",
        "topics": [
            (
                "Linear Regression",
                "Fit a line or hyperplane that predicts a continuous target from features.",
                r"\hat{y} = x^\top \theta",
                ["linear regression", "prediction", "features"],
                "A scatter plot with a fitted prediction line.",
            ),
            (
                "Mean Squared Error",
                "The loss function averages squared prediction errors over examples.",
                r"J(\theta)=\frac{1}{m}\sum_i(\hat{y}_i-y_i)^2",
                ["mean squared error", "loss function", "residual"],
                "Residual arrows from points to the regression line.",
            ),
            (
                "Normal Equation",
                "For full-rank linear regression, the closed-form optimum solves the least-squares objective.",
                r"\theta=(X^\top X)^{-1}X^\top y",
                ["normal equation", "closed form", "least squares"],
                "A matrix equation links X, y, and theta.",
            ),
            (
                "Bias and Variance",
                "Simple models may underfit while overly flexible models may overfit training data.",
                r"\mathrm{error}=bias^2+variance+\sigma^2",
                ["bias", "variance", "overfitting"],
                "Three curves compare underfit, good fit, and overfit behavior.",
            ),
        ],
    },
    {
        "lecture_id": "lec_02",
        "title": "Gradient Descent",
        "topics": [
            (
                "Gradient Descent",
                "Move parameters opposite to the gradient to reduce the objective.",
                r"\theta := \theta - \alpha \nabla_\theta J(\theta)",
                ["gradient descent", "optimization", "loss function"],
                "A point walks downhill on a loss surface.",
            ),
            (
                "Learning Rate",
                "The learning rate controls step size; too large can diverge and too small converges slowly.",
                r"\alpha > 0",
                ["learning rate", "step size", "convergence"],
                "Small and large arrows show different optimization step sizes.",
            ),
            (
                "Convex Loss",
                "For convex objectives, local minima are global minima.",
                r"J(\lambda a+(1-\lambda)b)\leq \lambda J(a)+(1-\lambda)J(b)",
                ["convexity", "global optimum", "loss function"],
                "A bowl-shaped curve marks the global minimum.",
            ),
            (
                "Stochastic Gradient",
                "Mini-batches estimate the gradient cheaply and add useful noise during training.",
                r"g_t \approx \nabla_\theta J_B(\theta)",
                ["stochastic gradient", "mini batch", "optimization"],
                "Noisy arrows move toward a minimum.",
            ),
        ],
    },
    {
        "lecture_id": "lec_03",
        "title": "Neural Networks",
        "topics": [
            (
                "Neural Network",
                "Layers compose linear maps and nonlinear activation functions to learn representations.",
                r"h=\sigma(Wx+b)",
                ["neural network", "representation", "activation function"],
                "Nodes and edges form a small feed-forward network.",
            ),
            (
                "Activation Function",
                "Nonlinear activations let networks model relationships beyond linear functions.",
                r"\mathrm{ReLU}(z)=\max(0,z)",
                ["activation function", "relu", "nonlinearity"],
                "A ReLU graph is flat for negative inputs and linear for positive inputs.",
            ),
            (
                "Chain Rule",
                "Backpropagation repeatedly applies the chain rule to compute gradients layer by layer.",
                r"\frac{\partial L}{\partial x}=\frac{\partial L}{\partial h}\frac{\partial h}{\partial x}",
                ["chain rule", "gradient", "calculus"],
                "A computational graph highlights local derivatives.",
            ),
            (
                "Backpropagation",
                "Backward passes propagate error signals so each weight receives a learning signal.",
                r"\frac{\partial L}{\partial W_l}=\delta_l h_{l-1}^\top",
                ["backpropagation", "neural network", "gradient descent"],
                "Arrows move backward from loss to earlier layers.",
            ),
        ],
    },
]


def font(size: int) -> ImageFont.ImageFont:
    for name in ["DejaVuSans.ttf", "Arial.ttf"]:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join([*current, word])
        if len(trial) > max_chars and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def draw_keyframe(path: Path, lecture_title: str, topic: str, description: str, formula: str, visual: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), "#f7f8fb")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 1280, 92], fill="#172554")
    draw.text((48, 28), "OmniCourse Lens", fill="#dbeafe", font=font(24))
    draw.text((320, 24), lecture_title, fill="white", font=font(34))
    draw.rounded_rectangle([60, 130, 1220, 650], radius=24, fill="white", outline="#cbd5e1", width=3)
    draw.text((100, 160), topic, fill="#0f172a", font=font(44))
    y = 235
    for line in wrap_text(description, 70):
        draw.text((105, y), line, fill="#334155", font=font(28))
        y += 38
    draw.rounded_rectangle([100, 370, 1180, 470], radius=14, fill="#eff6ff", outline="#93c5fd", width=2)
    draw.text((128, 400), formula, fill="#1d4ed8", font=font(32))
    draw.text((105, 520), "Visual evidence:", fill="#64748b", font=font(24))
    for line in wrap_text(visual, 78):
        draw.text((105, 555), line, fill="#0f766e", font=font(25))
    image.save(path)


def make_video_from_frames(lecture_dir: Path, frame_paths: list[Path], output_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        return
    concat_file = lecture_dir / "frames.txt"
    lines = []
    for frame in frame_paths:
        lines.append(f"file '{frame.resolve()}'")
        lines.append("duration 20")
    lines.append(f"file '{frame_paths[-1].resolve()}'")
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-vf",
            "format=yuv420p",
            "-r",
            "25",
            str(output_path),
        ],
        check=False,
    )
    concat_file.unlink(missing_ok=True)


def build_course() -> Course:
    lectures: list[Lecture] = []
    for lecture in LECTURES:
        lecture_id = lecture["lecture_id"]
        lecture_title = lecture["title"]
        frame_dir = settings.frames_dir / COURSE_ID / lecture_id
        video_path = settings.clips_dir / f"{COURSE_ID}_{lecture_id}.mp4"
        moments: list[Moment] = []
        frame_paths: list[Path] = []
        for index, (topic, description, formula, tags, visual) in enumerate(lecture["topics"]):
            start = float(index * 40)
            end = start + 35.0
            frame_path = frame_dir / f"{index + 1:02d}_{topic.lower().replace(' ', '_')}.png"
            draw_keyframe(frame_path, lecture_title, topic, description, formula, visual)
            frame_paths.append(frame_path)
            transcript = f"In this segment we study {topic.lower()}. {description}"
            ocr_text = f"{lecture_title}. {topic}. {description} Formula: {formula}. {visual}"
            moment_id = f"{COURSE_ID}_{lecture_id}_{index + 1:03d}"
            moments.append(
                Moment(
                    moment_id=moment_id,
                    course_id=COURSE_ID,
                    lecture_id=lecture_id,
                    start_time=start,
                    end_time=end,
                    transcript=transcript,
                    asr_segments=[
                        ASRSegment(
                            start_time=start,
                            end_time=end,
                            text=transcript,
                            confidence=0.98,
                            provider="demo_asr",
                        )
                    ],
                    ocr_text=ocr_text,
                    ocr_blocks=[
                        OCRBlock(
                            text=topic,
                            bbox=[100, 160, 900, 215],
                            confidence=0.99,
                            provider="demo_ocr",
                            frame_path=str(frame_path),
                            timestamp=start + 5,
                        ),
                        OCRBlock(
                            text=formula,
                            bbox=[128, 390, 1180, 450],
                            confidence=0.95,
                            provider="demo_ocr",
                            frame_path=str(frame_path),
                            timestamp=start + 5,
                        ),
                    ],
                    formula_latex=formula,
                    formula_blocks=[
                        FormulaBlock(
                            latex=formula,
                            source_frame=str(frame_path),
                            confidence=0.94,
                            timestamp=start + 5,
                            provider="demo_math_ocr",
                        )
                    ],
                    visual_caption=visual,
                    concept_tags=tags,
                    keyframes=[str(frame_path)],
                    thumbnail_url=static_url(frame_path),
                    metadata={"demo": True, "topic": topic},
                )
            )
        make_video_from_frames(frame_dir, frame_paths, video_path)
        lectures.append(
            Lecture(
                lecture_id=lecture_id,
                course_id=COURSE_ID,
                title=lecture_title,
                video_path=str(video_path) if video_path.exists() else None,
                duration=160.0,
                moments=moments,
                metadata={"generated_demo": True},
            )
        )
    return Course(
        course_id=COURSE_ID,
        title="Machine Learning Foundations",
        description="Deterministic demo course for multimodal lecture search over ASR, OCR, formulas, and visuals.",
        lectures=lectures,
    )


def main() -> None:
    ensure_directories()
    course = build_course()
    path = save_course(course)
    print(f"Wrote {path}")
    print(f"Lectures: {len(course.lectures)}")
    print(f"Moments: {sum(len(lecture.moments) for lecture in course.lectures)}")


if __name__ == "__main__":
    main()
