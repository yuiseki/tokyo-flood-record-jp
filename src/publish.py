#!/usr/bin/env python3
"""Push the card, the licence, the provenance, the Parquet and the raw zips to the Hub.

The source overwrites its files in place, so the Hub holds one run only: the newest under
data/raw/. Each zip goes up unchanged after its sha256 is checked against MANIFEST.json.

    uv run python src/publish.py             # dry run: list the files and their total size
    uv run python src/publish.py --push
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPO = "yuiseki/tokyo-flood-record-jp"
DELETE_PATTERNS = ["raw/**", "parquet/**"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(data: Path) -> list[str]:
    card = (data / "README.md").read_text(encoding="utf-8")
    if "license: cc-by-4.0" not in card:
        raise SystemExit("the card does not declare license: cc-by-4.0")
    runs = sorted((data / "raw").glob("*/MANIFEST.json"))
    if not runs:
        raise SystemExit("no run under data/raw/; run scripts/01_download.py")
    d = runs[-1].parent
    if f"raw/{d.name}/" not in card:
        raise SystemExit(f"the card does not name the current run raw/{d.name}/")
    manifest = json.loads((d / "MANIFEST.json").read_text())
    cols = json.loads((data / "parquet" / "columns.json").read_text())
    for t, n in cols["counts"].items():
        if f"{n:,}" not in card:
            raise SystemExit(f"the card does not give the row count {n:,} of {t}")
    zips = [k for k in manifest["files"] if k[:4].isdigit()]
    if len(zips) != 43:
        raise SystemExit(f"{len(zips)} zips in the manifest, expected 43")
    files = ["README.md", "LICENSE", "provenance.yaml", f"raw/{d.name}/MANIFEST.json"]
    for key, e in manifest["files"].items():
        if sha256(d / key) != e["sha256"]:
            raise SystemExit(f"{d / key} is not the file in its manifest")
        files.append(f"raw/{d.name}/{key}")
    files += ["parquet/columns.json"]
    files += [f"parquet/{t}.parquet" for t in cols["counts"]]
    missing = [f for f in files if not (data / f).is_file()]
    if missing:
        raise SystemExit(f"missing: {missing[:5]}")
    on_disk = {p.relative_to(data).as_posix() for p in data.rglob("*") if p.is_file()}
    stray = {f for f in on_disk - set(files) if not f.startswith("docs/")}
    if stray:
        raise SystemExit(f"files under data/ that are not published: {sorted(stray)[:5]}")
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()
    files = collect(DATA)
    total = sum((DATA / f).stat().st_size for f in files)
    print(f"{a.repo}\n  {len(files)} files, {total:,} bytes ({total / 1e6:.1f} MB)")
    if not a.push:
        print("\ndry run. pass --push to upload")
        return 0
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(a.repo, repo_type="dataset", exist_ok=True, private=False)
    api.upload_folder(folder_path=str(DATA), repo_id=a.repo, repo_type="dataset",
                      allow_patterns=files, delete_patterns=DELETE_PATTERNS)  # fmt: skip
    print(f"\npushed to https://huggingface.co/datasets/{a.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
