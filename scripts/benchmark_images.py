"""Interleaved local-only image benchmark; never fetches an external service."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import platform
import secrets
import statistics
import subprocess
import sys
import time
import types
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nova_slider_captcha import images


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ref", default="HEAD")
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    if not 5 <= args.iterations <= 100:
        parser.error("iterations must be from 5 to 100")
    revision = subprocess.check_output(["git", "rev-parse", args.baseline_ref], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(["git", "show", f"{revision}:src/nova_slider_captcha/images.py"], cwd=ROOT)
    baseline = types.ModuleType("nova_slider_captcha._image_baseline")
    baseline.__package__ = "nova_slider_captcha"
    exec(compile(source, "baseline/images.py", "exec"), baseline.__dict__)
    records = {"baseline": [], "candidate": []}
    functions = {"baseline": baseline.make_puzzle, "candidate": images.make_puzzle}
    save = Image.Image.save
    def sample(name, seed):
        png_time = 0
        def timed_save(instance, *positional, **keyword):
            nonlocal png_time
            start = time.perf_counter()
            try:
                return save(instance, *positional, **keyword)
            finally:
                png_time += time.perf_counter() - start
        with patch.object(Image.Image, "save", timed_save), patch.object(secrets, "randbelow", side_effect=(20, 20)), patch.object(secrets, "randbits", return_value=seed):
            started = time.perf_counter()
            result = functions[name]()
            elapsed = time.perf_counter() - started
        sizes = [len(base64.b64decode(uri.split(",", 1)[1])) for uri in result[2:]]
        return {"total_ms": elapsed * 1000, "png_ms": png_time * 1000, "background_bytes": sizes[0], "piece_bytes": sizes[1]}, result
    for i in range(3):
        for name in functions:
            sample(name, i)
    preview = {}
    for i in range(args.iterations):
        seed = secrets.randbits(128)
        for name in (("baseline", "candidate") if i % 2 == 0 else ("candidate", "baseline")):
            record, result = sample(name, seed)
            records[name].append(record)
            if i == 0:
                preview[name] = result
    summary = {name: {key: {"median": statistics.median(row[key] for row in rows), "min": min(row[key] for row in rows), "max": max(row[key] for row in rows)} for key in rows[0]} for name, rows in records.items()}
    report = {"baseline_revision": revision, "candidate_sha256": hashlib.sha256(Path(images.__file__).read_bytes()).hexdigest(), "python": platform.python_version(), "pillow": Image.__version__, "iterations_per_algorithm": args.iterations, "order": "alternating paired samples, same interpreter and seed per pair", "summary": summary, "samples": records, "limitations": ["Local microbenchmark, not production throughput or bot resistance", "No URLs, requests or production data; paired synthetic samples only"]}
    with args.output.open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    if args.preview:
        # Synthetic, flattened comparison sheet; no seeds or machine answers.
        sheet = Image.new("RGB", (images.WIDTH * 2, images.HEIGHT + images.PIECE_SIZE), "white")
        import io
        for column, name in enumerate(("baseline", "candidate")):
            result = preview[name]
            for row, uri in enumerate(result[2:]):
                bitmap = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
                sheet.paste(bitmap, (column * images.WIDTH, row * images.HEIGHT), bitmap if bitmap.mode == "RGBA" else None)
        sheet.save(args.preview)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
