#!/usr/bin/env python3
"""Build an Xcursor theme from the Windows 11 cursor pack."""
import os
import shutil
import sys

import xcursor as X

SRC = os.environ.get("CURSOR_PACK", "/mnt/HDD_0/Program/鼠标指针")
VARIANT = sys.argv[1] if len(sys.argv) > 1 else "light/regular"
COLOR = sys.argv[2] if len(sys.argv) > 2 else "01. default"
THEME = sys.argv[3] if len(sys.argv) > 3 else "W11-Light-default"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", THEME)
BASE = os.path.join(SRC, VARIANT, "base")
COLORDIR = os.path.join(SRC, VARIANT, COLOR)
if not os.path.isdir(COLORDIR):
    # tolerate the "08 purple" vs "08. purple" style naming differences
    cands = [d for d in os.listdir(os.path.join(SRC, VARIANT))
             if d.split(". ")[0] == COLOR.split(". ")[0] and os.path.isdir(os.path.join(SRC, VARIANT, d))]
    if not cands:
        raise SystemExit(f"no such color variant: {COLORDIR}")
    COLORDIR = os.path.join(SRC, VARIANT, cands[0])

# cursor file -> list of Xcursor names it is installed under
CURSORS = {
    "pointer.cur": ["left_ptr", "default", "arrow", "top_left_arrow", "left_arrow",
                    "context-menu", "copy", "alias", "zoom-in", "zoom-out",
                    "dnd-copy"],
    "beam.cur": ["text", "xterm", "ibeam", "vertical-text"],
    "precision.cur": ["crosshair", "cross", "cross_reverse", "tcross", "cell",
                      "color-picker"],
    "handwriting.cur": ["pencil", "draft", "handwriting"],
    "link.cur": ["hand2", "pointer", "pointing_hand", "hand", "hand1", "dnd-link"],
    "unavailable.cur": ["not-allowed", "crossed_circle", "no-drop", "forbidden",
                        "dnd-no-drop"],
    "vert.cur": ["ns-resize", "v_double_arrow", "sb_v_double_arrow", "size_ver",
                 "top_side", "bottom_side", "row-resize", "n-resize", "s-resize"],
    "horz.cur": ["ew-resize", "h_double_arrow", "sb_h_double_arrow", "size_hor",
                 "left_side", "right_side", "col-resize", "e-resize", "w-resize"],
    "dgn1.cur": ["nwse-resize", "size_fdiag", "size-fdiag", "fdiag",
                 "top_left_corner", "bottom_right_corner", "nw-resize", "se-resize"],
    "dgn2.cur": ["nesw-resize", "size_bdiag", "size-bdiag", "bdiag",
                 "top_right_corner", "bottom_left_corner", "ne-resize", "sw-resize"],
    "move.cur": ["move", "fleur", "all-scroll", "size_all", "grab", "grabbing",
                 "openhand", "closedhand", "dnd-none", "dnd-move"],
    "alternate.cur": ["up_arrow", "sb_up_arrow", "center_ptr"],
    "help.cur": ["help", "question_arrow", "whats_this", "left_ptr_help", "dnd-ask"],
    "person.cur": ["person", "user"],
    "pin.cur": ["pin", "location"],
}

ANIM = {
    "working.ani": ["left_ptr_watch", "progress", "half-busy", "appstarting"],
    "busy.ani": ["watch", "wait", "busy"],
}


def _sizes(frames):
    return sorted({im["w"] for fr in frames for im in fr})


def anim_source(fn):
    """Pick the best file for an .ani cursor.

    The light '01. default' pack ships a 32px-only busy.ani while the dark pack
    has the identical animation at full resolution; borrow it when the frames
    actually match.
    """
    import numpy as np

    path = os.path.join(COLORDIR, fn)
    frames, delays = X.parse_ani(path)
    if _sizes(frames) == [32]:
        polarity, rest = VARIANT.split("/", 1)
        other = os.path.join(SRC, "dark" if polarity == "light" else "light", rest,
                             os.path.basename(COLORDIR), fn)
        if os.path.exists(other):
            oframes, odelays = X.parse_ani(other)
            if 96 in _sizes(oframes) and len(oframes) == len(frames):
                same = all(
                    np.array_equal([i for i in fa if i["w"] == 32][0]["rgba"],
                                   [i for i in fb if i["w"] == 32][0]["rgba"])
                    for fa, fb in zip(frames, oframes))
                if same:
                    print(f"note: {fn} is 32px-only, using identical hi-res animation "
                          f"from {os.path.relpath(other, SRC)}")
                    return oframes, odelays
    return frames, delays


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    cdir = os.path.join(OUT, "cursors")
    os.makedirs(cdir)

    total = 0
    report = []
    for fn, names in CURSORS.items():
        ims = X.load_cur(os.path.join(BASE, fn))
        images = X.frames_to_xcursor([ims], [0])
        primary = names[0]
        path = os.path.join(cdir, primary)
        X.write_xcursor(path, images)
        total += os.path.getsize(path)
        report.append((primary, len(images), [i["size"] for i in images]))
        for alias in names[1:]:
            os.symlink(primary, os.path.join(cdir, alias))

    for fn, names in ANIM.items():
        frames, delays = anim_source(fn)
        images = X.frames_to_xcursor(frames, delays)
        primary = names[0]
        path = os.path.join(cdir, primary)
        X.write_xcursor(path, images)
        total += os.path.getsize(path)
        sizes = sorted({i["size"] for i in images})
        report.append((primary, len(images), sizes))
        for alias in names[1:]:
            os.symlink(primary, os.path.join(cdir, alias))

    with open(os.path.join(OUT, "index.theme"), "w") as f:
        f.write("[Icon Theme]\n"
                f"Name={THEME}\n"
                "Comment=Windows 11 cursor pack converted to Xcursor\n"
                "Inherits=Adwaita\n")
    with open(os.path.join(OUT, "cursor.theme"), "w") as f:
        f.write(f"[Icon Theme]\nName={THEME}\nInherits=Adwaita\n")

    print(f"theme: {THEME}")
    print(f"source: {VARIANT}/{os.path.basename(COLORDIR)}")
    print(f"files: {len(os.listdir(cdir))} entries, {total/1048576:.2f} MiB")
    for r in report:
        print("  %-16s %3d images  sizes=%s" % r)


if __name__ == "__main__":
    main()
