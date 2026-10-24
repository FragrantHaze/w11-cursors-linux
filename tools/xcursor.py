#!/usr/bin/env python3
"""Windows .cur/.ani  ->  Xcursor theme converter.

Parses Windows cursor files (32-bit DIB or PNG payloads) and writes
standard Xcursor files that libXcursor / niri / GTK can load.
"""
import struct
import numpy as np

# ---------------------------------------------------------------- Windows .cur


def _dib_to_rgba(blob):
    hdr = struct.unpack_from('<IiiHHIIiiII', blob, 0)
    bi_size, bi_w, bi_h, bi_planes, bi_bits, bi_comp = hdr[0], hdr[1], hdr[2], hdr[3], hdr[4], hdr[5]
    if bi_comp != 0 or bi_bits not in (1, 4, 8, 24, 32):
        raise ValueError(f"unsupported DIB: {bi_bits}bpp comp={bi_comp}")
    w, h2 = bi_w, bi_h
    h = h2 // 2                       # XOR bitmap + AND mask
    off = bi_size                     # palette follows the header for <=8bpp

    if bi_bits <= 8:
        clr_used = struct.unpack_from('<I', blob, 32)[0] or (1 << bi_bits)
        pal = np.frombuffer(blob, dtype=np.uint8, count=clr_used * 4,
                            offset=off).reshape(-1, 4)[:, 2::-1]
        off += clr_used * 4

    stride = ((w * bi_bits + 31) // 32) * 4
    raw = np.frombuffer(blob, dtype=np.uint8, count=stride * h, offset=off)
    rows = raw.reshape(h, stride)[::-1]

    if bi_bits == 32:
        bgra = np.ascontiguousarray(rows).view(np.uint8).reshape(h, w, 4)
        rgba = np.empty((h, w, 4), np.uint8)
        rgba[..., 0] = bgra[..., 2]
        rgba[..., 1] = bgra[..., 1]
        rgba[..., 2] = bgra[..., 0]
        rgba[..., 3] = bgra[..., 3]
    elif bi_bits == 24:
        bgr = np.ascontiguousarray(rows).reshape(h, stride // 3, 3)[:, :w]
        rgba = np.empty((h, w, 4), np.uint8)
        rgba[..., 0] = bgr[..., 2]
        rgba[..., 1] = bgr[..., 1]
        rgba[..., 2] = bgr[..., 0]
        rgba[..., 3] = 255
    else:
        bits = np.unpackbits(rows, axis=1)
        if bi_bits == 8:
            idx = bits[:, :w]
        else:
            idx = bits[:, :w * bi_bits].reshape(h, w, bi_bits)
            idx = (idx * (1 << np.arange(bi_bits - 1, -1, -1, dtype=np.uint8))).sum(axis=2)
        rgba = np.empty((h, w, 4), np.uint8)
        rgb = pal[idx.astype(np.intp)] if len(pal) > 1 else np.zeros((h, w, 3), np.uint8)
        rgba[..., :3] = rgb
        rgba[..., 3] = 255

    if bi_bits < 32 or not rgba[..., 3].any():   # alpha from AND mask
        mstride = ((w + 31) // 32) * 4
        mo = off + stride * h
        mask = np.frombuffer(blob, dtype=np.uint8, count=mstride * h, offset=mo)
        bits = np.unpackbits(mask.reshape(h, mstride)[::-1], axis=1)[:, :w]
        rgba[..., 3] = np.where(bits == 1, 0, 255).astype(np.uint8)
    return w, h, rgba


def parse_cur_bytes(data):
    """Return list of dicts: {w,h,xhot,yhot,rgba}."""
    if data[:8] == b'\x89PNG\r\n\x1a\n':          # bare PNG, treat as 0,0 hotspot
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data)).convert('RGBA')
        return [dict(w=img.width, h=img.height, xhot=0, yhot=0,
                     rgba=np.array(img))]

    reserved, ctype, count = struct.unpack_from('<HHH', data, 0)
    if reserved != 0 or ctype not in (1, 2):
        raise ValueError(f"not a cur/ico (type={ctype})")
    out = []
    for i in range(count):
        w, h, _cc, _res, xhot, yhot, size, pos = struct.unpack_from('<BBBBHHII', data, 6 + i * 16)
        blob = data[pos:pos + size]
        if blob[:8] == b'\x89PNG\r\n\x1a\n':
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(blob)).convert('RGBA')
            rgba = np.array(img)
            ww, hh = img.width, img.height
        else:
            ww, hh, rgba = _dib_to_rgba(blob)
        if ctype == 1:            # plain icon: no hotspot stored
            xhot, yhot = ww // 2, hh // 2
        out.append(dict(w=ww, h=hh, xhot=xhot, yhot=yhot, rgba=rgba))
    return out


def load_cur(path):
    with open(path, 'rb') as f:
        return parse_cur_bytes(f.read())


# ---------------------------------------------------------------- Windows .ani


def parse_ani(path):
    """Return (frames, delays_ms). frames[i] = list of image dicts (multi-size)."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] != b'RIFF' or data[8:12] != b'ACON':
        raise ValueError("not an ANI file")
    nframes = nsteps = rate = None
    icons = []
    rates = None
    seq = None
    i = 12
    while i + 8 <= len(data):
        cid = data[i:i + 4]
        sz = struct.unpack_from('<I', data, i + 4)[0]
        body = data[i + 8:i + 8 + sz]
        if cid == b'anih':
            (_cb, nframes, nsteps, _w, _h, _bits, _planes, rate, _flags) = struct.unpack('<9I', body[:36])
        elif cid == b'LIST' and body[:4] == b'fram':
            j = 4
            while j + 8 <= len(body):
                sid = body[j:j + 4]
                ssz = struct.unpack_from('<I', body, j + 4)[0]
                if sid == b'icon':
                    icons.append(body[j + 8:j + 8 + ssz])
                j += 8 + ssz + (ssz & 1)
        elif cid == b'rate':
            rates = list(struct.unpack_from('<%dI' % (sz // 4), body, 0))
        elif cid == b'seq ':
            seq = list(struct.unpack_from('<%dI' % (sz // 4), body, 0))
        i += 8 + sz + (sz & 1)

    if nframes:
        icons = icons[:nframes]
    if not icons:
        raise ValueError("no frames in ANI")
    frames = [parse_cur_bytes(b) for b in icons]

    jiffies = rate if rate else 6
    delays = [max(1, round(j / 60.0 * 1000)) for j in ([jiffies] * len(frames))]
    if rates:
        if len(rates) == 1:
            delays = [max(1, round(rates[0] / 60.0 * 1000))] * len(frames)
        else:
            d = [max(1, round(r / 60.0 * 1000)) for r in rates]
            delays = [d[k % len(d)] for k in range(len(frames))]
    if seq:
        frames = [frames[k % len(frames)] for k in seq]
        delays = [delays[k % len(delays)] for k in seq]
    return frames, delays


# ---------------------------------------------------------------- Xcursor out

XCURSOR_IMAGE_TYPE = 0xfffd0002
XCURSOR_MAGIC = 0x72756358      # 'Xcur'
XCURSOR_FILE_VERSION = 0x00010000
XCURSOR_FILE_HEADER_LEN = 16
XCURSOR_FILE_TOC_LEN = 12
XCURSOR_IMAGE_HEADER_LEN = 36
XCURSOR_IMAGE_VERSION = 1


def despeckle(rgba, weak=3, strong=24):
    """Drop islands of (nearly) transparent pixels.

    The Windows pack has stray RGB=255 / alpha=1 pixels floating outside the
    artwork; they are invisible only if the compositor does a strict
    premultiplied blend, and show up as white dust otherwise.
    """
    a = rgba[..., 3]
    weak_mask = a <= weak
    strong_mask = a >= strong
    if not weak_mask.any() or not strong_mask.any():
        return rgba
    h, w = a.shape
    seen = np.zeros_like(weak_mask)
    for y in range(h):
        for x in range(w):
            if not weak_mask[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            comp = []
            touches = False
            while stack:
                cy, cx = stack.pop()
                comp.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w:
                            if strong_mask[ny, nx]:
                                touches = True
                            elif weak_mask[ny, nx] and not seen[ny, nx]:
                                seen[ny, nx] = True
                                stack.append((ny, nx))
            if not touches:
                for cy, cx in comp:
                    rgba[cy, cx, 3] = 0
    return rgba


def _premultiply(px):
    """Xcursor stores premultiplied ARGB, same as X11/wl_shm ARGB32."""
    a = px[..., 3].astype(np.uint32)
    out = np.empty_like(px)
    for c in range(3):
        out[..., c] = ((px[..., c].astype(np.uint32) * a + 127) // 255).astype(np.uint8)
    out[..., 3] = px[..., 3]
    return out


def write_xcursor(path, images):
    """images: list of dict(w,h,xhot,yhot,size,delay,rgba) in file order."""
    ntoc = len(images)
    out = bytearray()
    out += struct.pack('<IIII', XCURSOR_MAGIC, XCURSOR_FILE_HEADER_LEN,
                       XCURSOR_FILE_VERSION, ntoc)
    pos = XCURSOR_FILE_HEADER_LEN + ntoc * XCURSOR_FILE_TOC_LEN
    toc = bytearray()
    chunks = bytearray()
    for im in images:
        toc += struct.pack('<III', XCURSOR_IMAGE_TYPE, im['size'], pos)
        assert im['rgba'].shape == (im['h'], im['w'], 4), (im['rgba'].shape, im['w'], im['h'])
        px = _premultiply(despeckle(im['rgba'].copy()))
        argb = (px[..., 3].astype(np.uint32) << 24 |
                px[..., 0].astype(np.uint32) << 16 |
                px[..., 1].astype(np.uint32) << 8 |
                px[..., 2].astype(np.uint32))
        data = struct.pack('<IIIIIIIII', XCURSOR_IMAGE_HEADER_LEN, XCURSOR_IMAGE_TYPE,
                           im['size'], XCURSOR_IMAGE_VERSION, im['w'], im['h'],
                           im['xhot'], im['yhot'], im['delay']) + argb.astype('<u4').tobytes()
        chunks += data
        pos += len(data)
    with open(path, 'wb') as f:
        f.write(out + toc + chunks)


def frames_to_xcursor(frames, delays, hotspot_override=None):
    """Take [frames][sizes] image dicts and group per nominal size.

    Output order: for each size (ascending), all animation frames in order.
    """
    sizes = sorted({im['w'] for fr in frames for im in fr if im['w'] == im['h']})
    out = []
    for size in sizes:
        for fi, fr in enumerate(frames):
            cand = [im for im in fr if im['w'] == size and im['h'] == size]
            if not cand:
                continue
            im = cand[0]
            xh, yh = im['xhot'], im['yhot']
            if hotspot_override:
                xh, yh = hotspot_override
            out.append(dict(w=im['w'], h=im['h'], xhot=xh, yhot=yh,
                            size=size, delay=delays[fi] if len(frames) > 1 else 0,
                            rgba=im['rgba']))
    return out
