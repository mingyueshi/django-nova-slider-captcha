"""Run the exact CI triples using implementation-owned environments/databases."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, default=Path("/tmp/nova-slider-residual-impl-dist-20261026/nova_slider_captcha-0.3.0-py3-none-any.whl"))
    parser.add_argument("--modes", default="source,wheel")
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    modes = args.modes.split(",")
    assert all(mode in ("source", "wheel") for mode in modes)
    cells = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())["jobs"]["django"]["strategy"]["matrix"]["include"]
    def cell(spec):
        name = "py" + spec["python"].replace(".", "") + "-dj" + spec["django"].replace(".", "") + "-pil" + spec["pillow"].replace(".", "")[:-1]
        # Runtime directory names keep Pillow's major/minor (122 / 123).
        name = "py" + spec["python"].replace(".", "") + "-dj" + spec["django"].replace(".", "") + "-pil" + "".join(spec["pillow"].split(".")[:2])
        python = Path(f"/tmp/nova-slider-residual-impl-{name}-20261026/bin/python")
        record = {**spec, "profiles": []}
        log_path = OUT / f"{name}-{args.label}.log"
        with log_path.open("x") as log:
            def run(command, env):
                log.write("$ " + " ".join(map(str, command)) + "\n")
                log.flush()
                subprocess.run(list(map(str, command)), cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            for mode in modes:
                env = os.environ.copy()
                env.update(PYTHONPATH="src:." if mode == "source" else ".", DJANGO_SETTINGS_MODULE="tests.settings", PYTHONDONTWRITEBYTECODE="1", NOVA_TEST_DB=f"/tmp/nova-slider-residual-impl-{name}-{mode}.sqlite3")
                if mode == "wheel":
                    run(["uv", "pip", "install", "--python", python, "--no-deps", "--reinstall", args.wheel], env)
                expected = (ROOT / "src").resolve() if mode == "source" else python.parents[1].resolve()
                run([python, "-c", f"import platform,pathlib,django,PIL,nova_slider_captcha; p=pathlib.Path(nova_slider_captcha.__file__).resolve(); print(platform.python_version(),django.get_version(),PIL.__version__,p); assert platform.python_version().startswith({spec['python']!r}+'.'); assert django.get_version()=={spec['django']!r}; assert PIL.__version__=={spec['pillow']!r}; assert p.is_relative_to(pathlib.Path({str(expected)!r}))"], env)
                for command in (("check",), ("makemigrations", "nova_slider_captcha", "--check", "--dry-run"), ("test", "tests", "--noinput", "-v", "1")):
                    run([python, "-m", "django", *command], env)
                run(["uv", "pip", "check", "--python", python], env)
                counts = re.findall(r"Ran (\d+) tests? in", log_path.read_text())
                assert counts and int(counts[-1]) > 0
                record["profiles"].append({"mode": mode, "tests": int(counts[-1]), "status": "passed"})
        print(json.dumps(record), flush=True)
        return record
    with ThreadPoolExecutor(max_workers=2) as executor:
        records = list(executor.map(cell, cells))
    artifact = {"wheel": str(args.wheel), "sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest()} if "wheel" in modes else None
    with (OUT / f"matrix-{args.label}.json").open("x") as output:
        json.dump({"artifact": artifact, "cells": records}, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
