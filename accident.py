"""Heuristic accident cues from tracked vehicle boxes (needs tracker IDs). Demo logic: expect false alarms.
Cue 1 collision: two vehicles that were moving overlap and both stop. Cue 2 stalled: a vehicle that was moving
sits still for a long time while most other traffic keeps moving. Speeds are in frame-widths per second."""
MOVE, STOP = .05, .012

def iou(a, b):
    i = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0

class AccidentDetector:
    def __init__(s, stall_s=8, hold_s=1.0): s.tr, s.pair, s.stall_s, s.hold_s = {}, {}, stall_s, hold_s

    def update(s, now, boxes, ids, width):
        cur = {}
        for b, i in zip(boxes, ids):
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2; p = s.tr.get(i); v, mov = 0.0, (p["mov"] if p else 0)
            if p: v = .6 * p["v"] + .4 * (((cx - p["cx"]) ** 2 + (cy - p["cy"]) ** 2) ** .5 / max(now - p["t"], 1e-3) / width)
            if v > MOVE: mov = now
            still = ((p["still"] or now) if p else None) if v < STOP else None
            cur[i] = dict(cx=cx, cy=cy, t=now, v=v, mov=mov, still=still, b=b)
        s.tr = {**{i: p for i, p in s.tr.items() if now - p["t"] < 3}, **cur}
        fr = list(cur); ev = None; alive = set()
        for a in range(len(fr)):
            for c in range(a + 1, len(fr)):
                i, j = fr[a], fr[c]; A, B = cur[i], cur[j]
                if iou(A["b"], B["b"]) > .2 and A["still"] and B["still"] and now - A["mov"] < 4 and now - B["mov"] < 4:
                    alive.add((i, j)); t0 = s.pair.setdefault((i, j), now)
                    if ev is None and now - t0 >= s.hold_s:
                        bb = [min(A["b"][0], B["b"][0]), min(A["b"][1], B["b"][1]), max(A["b"][2], B["b"][2]), max(A["b"][3], B["b"][3])]
                        ev = dict(kind="collision", ids=[i, j], box=bb)
        s.pair = {k: v for k, v in s.pair.items() if k in alive}
        for i in fr:
            A = cur[i]; others = [cur[j]["v"] for j in fr if j != i]
            if ev is None and A["still"] and A["mov"] > 0 and now - A["still"] >= s.stall_s and len(others) >= 3 and sum(v > .03 for v in others) >= .6 * len(others):
                ev = dict(kind="stalled vehicle", ids=[i], box=list(A["b"]))
        return ev
