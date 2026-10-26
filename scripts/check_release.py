"""Validate a stable release and exact built payload (Python 3.11+ tooling).

No upload capability. Called in the unprivileged build/tag jobs, never publish.
"""
import argparse
import ast
from email.parser import BytesParser
import json
from pathlib import Path
import re
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "nova_slider_captcha"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_version(root):
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    version = project["version"]
    require(re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version), "Expected a stable X.Y.Z version")
    require(project["name"] == "nova-slider-captcha", "Unexpected project name")
    module = ast.parse((root / "src" / PACKAGE / "__init__.py").read_text())
    versions = [ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)]
    require(versions == [version], "Python __version__ differs from project metadata")
    require(json.loads((root / "package.json").read_text())["version"] == version, "package.json version mismatch")
    lock = json.loads((root / "package-lock.json").read_text())
    require(lock["version"] == lock["packages"][""]["version"] == version, "package-lock.json version mismatch")
    require(f"# Nova Slider CAPTCHA {version}" in (root / "README.md").read_text(), "README version mismatch")
    return version


def check_dist(root, directory, version):
    paths = sorted(directory.iterdir())
    require(len(paths) == 2, "Expected exactly one wheel and one sdist")
    wheel = directory / f"{PACKAGE}-{version}-py3-none-any.whl"
    sdist = directory / f"{PACKAGE}-{version}.tar.gz"
    require(set(paths) == {wheel, sdist}, "Distribution filenames do not match the version")
    # Compare every runtime asset, including every migration and translation.
    runtime = {p.relative_to(root / "src").as_posix(): p.read_bytes() for p in (root / "src" / PACKAGE).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    require(runtime, "Empty runtime payload")
    with zipfile.ZipFile(wheel) as archive:
        for name, content in runtime.items():
            require(archive.read(name) == content, f"Wheel omitted or changed {name}")
        metadata = BytesParser().parsebytes(archive.read(f"{PACKAGE}-{version}.dist-info/METADATA"))
        require(metadata["Version"] == version and metadata["Name"] == "nova-slider-captcha", "Wheel metadata mismatch")
        require(metadata["Description-Content-Type"] == "text/markdown", "README is not Markdown metadata")
        for match in re.finditer(r"\]\(([^)]+)\)", metadata.get_payload()):
            require(match[1].startswith(("https://", "http://", "#")), f"PyPI README has a relative link: {match[1]}")
    with tarfile.open(sdist) as archive:
        prefix = f"{PACKAGE}-{version}/"
        for name, content in runtime.items():
            require(archive.extractfile(prefix + "src/" + name).read() == content, f"sdist omitted or changed {name}")
        metadata = BytesParser().parsebytes(archive.extractfile(prefix + "PKG-INFO").read())
        require(metadata["Version"] == version, "sdist metadata mismatch")
        for required in ("LICENSE", "README.md", "pyproject.toml", "scripts/test_policy_upgrade.py", "tests/test_policy.py"):
            require(prefix + required in archive.getnames(), f"sdist missing {required}")
    print(f"Verified {len(runtime)} runtime files in wheel and sdist for {version}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    parser.add_argument("--dist", type=Path)
    args = parser.parse_args()
    version = source_version(ROOT)
    if args.tag is not None:
        require(args.tag == "v" + version, "Release tag must exactly match v + project version")
    if args.dist is not None:
        check_dist(ROOT, args.dist, version)
    print(f"Release metadata consistent: {version}")


if __name__ == "__main__":
    main()
