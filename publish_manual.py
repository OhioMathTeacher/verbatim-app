#!/usr/bin/env python3
"""Turn a Google Docs / Word export of the manual into a PDF that is safe to publish.

Why this exists.

The manual's screenshots are cropped to keep one instructor's name and face out
of a public document. A crop in Word or Google Docs is not a redaction: it
records "display this rectangle" in `a:srcRect` and keeps every pixel of the
original. The hidden part survives the export -- including into the PDF, where
`pdfimages` recovers it in one command -- so a document that looks clean on
every page can still carry what the crop was meant to remove.

That is not a mistake anyone makes once. Every fresh export from Docs brings the
uncropped originals back, and the only way to see it is to go looking, which is
exactly what nobody does on the way out the door. So the flattening is a build
step, not a habit.

    python3 publish_manual.py                       # verbatim-user-manual.docx -> .pdf
    python3 publish_manual.py --check-only some.pdf  # is this PDF safe to publish?

Each image is cut down to the rectangle the document actually shows, its
`srcRect` is zeroed so the two agree, and the PDF is rendered from the result.
The check afterwards reads the images back out of the finished PDF, because the
only claim worth making is about the file that ships.
"""
import argparse, io, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

A   = "http://schemas.openxmlformats.org/drawingml/2006/main"
R   = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"

HERE    = Path(__file__).resolve().parent
DOCX    = HERE / "verbatim-user-manual.docx"
PDF     = HERE / "verbatim-user-manual.pdf"

# What must not survive into a published file. Add to it rather than relying on
# anyone remembering: the point is that the check outlives the memory of why.
FORBIDDEN = ("zheng", "scupi", "sichuan")


def flatten(src: Path, dst: Path) -> int:
    """Apply every crop destructively. Returns how many images were cut."""
    z    = zipfile.ZipFile(src)
    doc  = z.read("word/document.xml").decode("utf-8")
    rels = ET.fromstring(z.read("word/_rels/document.xml.rels"))
    target = {r.get("Id"): "word/" + r.get("Target").lstrip("/")
              for r in rels.iter(f"{{{PKG}}}Relationship")}

    jobs, seen = {}, {}
    for fill in ET.fromstring(doc).iter():
        if not fill.tag.endswith("blipFill"):
            continue
        blip, rect = fill.find(f"{{{A}}}blip"), fill.find(f"{{{A}}}srcRect")
        if blip is None or rect is None:
            continue
        rid  = blip.get(f"{{{R}}}embed")
        crop = tuple(int(rect.get(k, "0") or 0) for k in ("l", "t", "r", "b"))
        if not any(crop) or rid not in target:
            continue
        path = target[rid]
        # One media file shown twice with different crops cannot be flattened in
        # place -- it would need duplicating. Say so rather than silently pick one.
        if path in seen and seen[path] != crop:
            print(f"  !! {path} is displayed with two different crops — left alone")
            jobs.pop(path, None)
            continue
        seen[path], jobs[path] = crop, crop

    from PIL import Image
    cut = {}
    for path, (l, t, r, b) in jobs.items():
        im = Image.open(io.BytesIO(z.read(path)))
        W, H = im.size
        box = (round(W * l / 100000), round(H * t / 100000),
               W - round(W * r / 100000), H - round(H * b / 100000))
        buf = io.BytesIO()
        im.crop(box).save(buf, format=im.format or "PNG")
        cut[path] = buf.getvalue()
        print(f"  {Path(path).name}: {W}×{H} → {box[2]-box[0]}×{box[3]-box[1]}")

    doc = re.sub(r"<a:srcRect[^/>]*/>", "<a:srcRect/>", doc)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
        for item in z.infolist():
            if item.filename == "word/document.xml":
                out.writestr(item, doc)
            else:
                out.writestr(item, cut.get(item.filename) or z.read(item.filename))
    return len(cut)


def render(docx: Path, out_dir: Path) -> Path:
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(out_dir), str(docx)],
                   check=True, capture_output=True)
    return next(out_dir.glob("*.pdf"))


def check(pdf: Path) -> bool:
    """Read the images back out of the finished PDF and OCR them."""
    if not shutil.which("pdfimages"):
        print("  ?? pdfimages not installed — cannot verify, not claiming it is clean")
        return False
    ocr = shutil.which("tesseract")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdfimages", "-png", str(pdf), f"{tmp}/i"],
                       check=True, capture_output=True)
        imgs = sorted(Path(tmp).glob("i-*.png"))
        if not ocr:
            print(f"  ?? tesseract not installed — {len(imgs)} images left unread")
            return False
        bad = []
        for f in imgs:
            text = subprocess.run(["tesseract", str(f), "-"],
                                  capture_output=True, text=True).stdout.lower()
            hits = sorted({w for w in FORBIDDEN if w in text})
            if hits:
                bad.append((f.name, hits))
        for name, hits in bad:
            print(f"  !! {name} still contains {', '.join(hits)}")
        print(f"  {len(imgs) - len(bad)}/{len(imgs)} images clean")
        return not bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", type=Path, default=DOCX)
    ap.add_argument("--out",  type=Path, default=PDF)
    ap.add_argument("--check-only", type=Path,
                    help="verify a PDF that is already built, and change nothing")
    a = ap.parse_args()

    if a.check_only:
        print(f"checking {a.check_only}")
        ok = check(a.check_only)
        print("\nsafe to publish" if ok else "\nDO NOT PUBLISH")
        return 0 if ok else 1

    if not a.docx.exists():
        print(f"{a.docx} is not here. Export it from Google Docs first "
              f"(File → Download → Microsoft Word), then run this again.", file=sys.stderr)
        return 2

    print(f"flattening {a.docx.name}")
    n = flatten(a.docx, (tmp_docx := Path(tempfile.mkdtemp()) / a.docx.name))
    print(f"{n} image(s) flattened\n")

    print("rendering")
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(render(tmp_docx, Path(tmp)), a.out)
    print(f"  {a.out.name}  ({a.out.stat().st_size/1024:.0f} KB)\n")

    print("checking the file that ships")
    if not check(a.out):
        print("\nDO NOT PUBLISH — the built PDF still carries a name")
        return 1
    print("\nsafe to publish")
    return 0


if __name__ == "__main__":
    sys.exit(main())
