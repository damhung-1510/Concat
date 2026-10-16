#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Jareer and Concat contributors
"""Puts videos into a Thơ Hoài Cổ template, stretched to each video's length, and renders them.

    scripts/apply-tho-template.py TEMPLATE_SLUG VIDEO... [--suffix _hoainiem] [--out DIR] [--crf 26]

TEMPLATE_SLUG is a folder of the app's templates: tho-hoai-co, tho-hoai-co-chay-chu-2-trang or
tho-hoai-co-chay-chu-nhieu-trang. Each video becomes `name<suffix>.mp4` beside it (or in --out).
The template's picture, looks, dimming and fades run the whole video; a template with pages of
verse spreads them evenly over it, each page's words arriving across its own stretch. The verse,
title and author are still the template's placeholders, to retype afterwards.

It drives the engine through `concat-cli api`, so build that first:
    cargo build --profile quick -p concat-cli
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

LINEAR = [0.0, 0.0, 1.0, 1.0]
HERE = Path(__file__).resolve().parent
CLI = HERE.parent / "src/target/quick/concat-cli"
# What runs the whole length of the video.
WHOLE = {"vintage", "warm", "film-grain", "vignette", "dim"}


def templates_dir():
    if os.sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    elif os.sys.platform.startswith("win"):
        base = Path(os.environ["APPDATA"])
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "app.concat.editor/templates"


def duration(path):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
         "-of", "csv=p=0", str(path)]).decode())


def session(requests):
    proc = subprocess.Popen([str(CLI), "api"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True, bufsize=1)
    out = []
    for r in requests:
        proc.stdin.write(json.dumps(r) + "\n")
        proc.stdin.flush()
        out.append(proc.stdout.readline())
    proc.stdin.close()
    proc.wait()
    return out


def fade_in(length, seconds):
    return [dict(at=0.0, value=0.0, ease=LINEAR, property="opacity"),
            dict(at=round(min(seconds / length, 1.0), 4), value=1.0, ease=LINEAR, property="opacity")]


def stretch(project, dur):
    f = project / "concat.json"
    d = json.load(open(f))

    def revealed(c):
        return any(e["id"] == "concat.word-reveal" for e in c.get("videoEffects", []))

    def fix(clips):
        pages = sorted((c for c in clips if c["kind"] == "text" and revealed(c)),
                       key=lambda c: c["start"])
        if pages:
            span = (dur - 2.2) / len(pages)
            for n, c in enumerate(pages):
                c["start"] = round(1.2 + n * span, 3)
                c["duration"] = round(span - 0.4, 3)
        for c in clips:
            name = c["name"]
            if c["kind"] == "video" or name in WHOLE:
                c["duration"] = dur
            elif c["kind"] == "text" and not revealed(c) or name == "page rule":
                c["duration"] = round(dur - c["start"] - 0.2, 3)
                c["keys"] = fade_in(c["duration"], 0.9)
            elif name == "fade out":
                c["start"] = round(dur - c["duration"], 3)

    fix(d["clips"])
    for t in d["timelines"]:
        fix(t["clips"])
    json.dump(d, open(f, "w"), indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("template")
    ap.add_argument("videos", nargs="+", type=Path)
    ap.add_argument("--suffix", default="_hoainiem")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--crf", type=int, default=26)
    args = ap.parse_args()
    template = templates_dir() / args.template
    work = Path(tempfile.mkdtemp(prefix="tho-template-"))
    try:
        videos = [v.resolve() for v in args.videos]
        reqs = [{"method": "template.instantiate", "template": str(template), "location": str(work),
                 "name": v.stem, "fills": [{"mediaId": "m1", "file": str(v)}]} for v in videos]
        for v, r in zip(videos, session(reqs)):
            if '"error"' in r:
                raise SystemExit(f"{v.name}: {r[:300]}")
        for v in videos:
            stretch(work / v.stem, duration(v))
        cli = subprocess.Popen([str(CLI), "api"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               text=True, bufsize=1)

        def call(req):
            cli.stdin.write(json.dumps(req) + "\n")
            cli.stdin.flush()
            return cli.stdout.readline()

        for v in videos:
            out = (args.out or v.parent) / f"{v.stem}{args.suffix}.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            project = work / v.stem
            if '"error"' in call({"method": "project.open", "path": str(project)}):
                print("open failed", v.name, flush=True)
                continue
            part = f"{out}.part.mp4"
            r = call({"method": "export.run", "path": str(project), "output": part, "crf": args.crf})
            if '"error"' in r:
                print("export failed", v.name, r[:200], flush=True)
                continue
            while True:
                line = cli.stdout.readline()
                if not line:
                    raise SystemExit("concat-cli stopped")
                if "export.done" in line:
                    os.rename(part, out)
                    print("done", out, flush=True)
                    break
                if "export.failed" in line:
                    print("failed", v.name, line[:200], flush=True)
                    break
            call({"method": "project.close", "path": str(project)})
        cli.stdin.close()
        cli.wait()
    finally:
        shutil.rmtree(work, ignore_errors=True)


main()
