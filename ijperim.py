"""ImageJ-style perimeter of a binary mask: trace pixel-edge outlines, then
PolygonRoi.getTracedPerimeter on each outline (vertices only where direction changes)."""
import numpy as np

def outlines(mask, saddle_left=True):
    m = np.pad(mask, 1).astype(bool)
    H, W = m.shape
    nxt = {}
    # directed boundary edges with the foreground on the right (clockwise on screen, y down)
    # horizontal edges between rows y-1 and y at vertex row y
    ys, xs = np.nonzero(m[1:, :] & ~m[:-1, :])     # fg below, bg above: edge along top of pixel, going +x
    for y, x in zip(ys + 1, xs): nxt.setdefault((x, y), []).append((x + 1, y))
    ys, xs = np.nonzero(m[:-1, :] & ~m[1:, :])     # fg above, bg below: bottom of pixel, going -x
    for y, x in zip(ys + 1, xs): nxt.setdefault((x + 1, y), []).append((x, y))
    ys, xs = np.nonzero(m[:, :-1] & ~m[:, 1:])     # fg left, bg right: right side, going +y
    for y, x in zip(ys, xs + 1): nxt.setdefault((x, y), []).append((x, y + 1))
    ys, xs = np.nonzero(m[:, 1:] & ~m[:, :-1])     # fg right, bg left: left side, going -y
    for y, x in zip(ys, xs + 1): nxt.setdefault((x, y + 1), []).append((x, y))
    used = set(); loops = []
    for start, outs in list(nxt.items()):
        for o in outs:
            if (start, o) in used: continue
            loop = [start]; a, b = start, o
            while True:
                used.add((a, b)); loop.append(b)
                cands = [c for c in nxt[b] if (b, c) not in used]
                if not cands: break
                if len(cands) > 1:     # saddle: turn so the two diagonal pixels stay apart or join
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    right = (b[0] - dy, b[1] + dx); left = (b[0] + dy, b[1] - dx)
                    want = left if saddle_left else right
                    cands = [c for c in cands if c == want] or cands
                a, b = b, cands[0]
            loops.append(loop[:-1])
    return loops

def traced_perimeter(pts):
    xp = [p[0] for p in pts]; yp = [p[1] for p in pts]
    # keep only vertices where direction changes
    n = len(xp); keep = []
    for i in range(n):
        dx1, dy1 = xp[i] - xp[i - 1], yp[i] - yp[i - 1]
        dx2, dy2 = xp[(i + 1) % n] - xp[i], yp[(i + 1) % n] - yp[i]
        if (dx1, dy1) != (dx2, dy2): keep.append(i)
    xp = [xp[i] for i in keep]; yp = [yp[i] for i in keep]; n = len(xp)
    sumdx = sumdy = ncorners = 0
    dx1, dy1 = xp[0] - xp[-1], yp[0] - yp[-1]
    side1 = abs(dx1) + abs(dy1); corner = False
    for i in range(n):
        j = (i + 1) % n
        dx2, dy2 = xp[j] - xp[i], yp[j] - yp[i]
        sumdx += abs(dx1); sumdy += abs(dy1)
        side2 = abs(dx2) + abs(dy2)
        if side1 > 1 or not corner: corner = True; ncorners += 1
        else: corner = False
        dx1, dy1, side1 = dx2, dy2, side2
    return sumdx + sumdy - ncorners * (2 - np.sqrt(2))

def ij_perimeter(mask, saddle_left=True):
    return sum(traced_perimeter(l) for l in outlines(mask, saddle_left))
