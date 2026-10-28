"""Built-in queue-model simulator (no SUMO needed). Compares fixed-time, local queue-based
and GRIDGUARD (downstream-aware, counterfactual, closed-loop) on identical seeded demand.
Simulated proxies only: this is NOT SUMO output and does not control real signals."""
import numpy as np
NODES = ["J1", "J2", "J3", "J4", "J5"]
DOWN = {"J1": ["J2"], "J2": ["J3", "J4"], "J4": ["J3"], "J3": ["J5"], "J5": []}
STORE, DT, STEPS = 30, 10, 120
SCEN = {"normal": dict(lam=2.0), "peak": dict(lam=4.2),
        "blockage": dict(lam=3.4, block=(30, 70)), "saturation": dict(lam=3.6, sat=(30, 80)),
        "failure": dict(lam=3.6, block=(30, 70), fail=(35, 60))}
CANDS = {"Keep timing": {}, "A: extend green": {"ext": 1.5},
         "B: protect downstream": {"protect": 1}, "C: divert J2 to J4": {"divert": .3}}
inw = lambda w, t: bool(w) and w[0] <= t < w[1]

def step(q, t, sc, act, ctrl, arr, acc):
    for n, v in zip(("J1", "J2", "J4"), arr):
        q[n] += v
        if q[n] > STORE: acc["over"] += q[n] - STORE; q[n] = STORE
    acc["arr"] += sum(arr)
    for n in ("J5", "J3", "J4", "J2", "J1"):
        r = min(10, 4 + .35 * q[n]) if ctrl == "local" else 6.0
        gg = ctrl == "gg"
        if gg and n in ("J1", "J2"): r *= act.get("ext", 1)
        if n == "J5": r = 1.5 if inw(sc.get("sat"), t) else 8.0
        if n == "J3" and inw(sc.get("block"), t): r *= .15
        out = min(q[n], r)
        if n == "J5": q[n] -= out; acc["out"] += out; continue
        s4 = .25 + (act.get("divert", 0) if gg else 0)
        shares = {"J3": 1 - s4, "J4": s4} if n == "J2" else {DOWN[n][0]: 1.0}
        sent = 0
        for tg, sh in shares.items():
            want, free = out * sh, max(0, STORE - q[tg])
            if free < want - .05: acc["blk"] += 1
            if gg and act.get("protect") and n in ("J1", "J2") and free < .4 * STORE: want *= free / (.4 * STORE)
            amt = min(want, free); q[tg] += amt; sent += amt
        q[n] -= sent
    acc["vs"] += sum(q.values()) * DT

def node_risk(q, prev, n):
    Q = q[n] / STORE; O = min(1, Q * 1.15); G = min(1, max(0, (q[n] - prev[n]) / 6))
    D = max([q[d] / STORE for d in DOWN[n]] or [0])
    return .35 * Q + .25 * O + .2 * G + .2 * D

def cost(q, t, sc, act, lam):
    q2, a = dict(q), dict(vs=0, blk=0, over=0, arr=0, out=0)
    for _ in range(6): step(q2, t, sc, act, "gg", (lam, .4 * lam, .3 * lam), a)
    return .4 * a["vs"] / DT / 6 + .3 * max(q2.values()) + 2 * a["blk"] + .5 * a["over"]

def run_one(ctrl, sc, seed):
    rng = np.random.default_rng(seed); lam = sc["lam"]
    A = [(rng.poisson(lam), rng.poisson(.4 * lam), rng.poisson(.3 * lam)) for _ in range(STEPS)]
    q = {n: 2.0 for n in NODES}; acc = dict(vs=0, blk=0, over=0, arr=0, out=0); hist = [dict(q)]
    tl = dict(total=[], maxrisk=[], nodes={n: [] for n in NODES}); log = []
    chosen, pre, ban, sw, mq = "Keep timing", None, {}, 0, 0
    for t in range(STEPS):
        if ctrl == "gg" and t % 3 == 0:
            tot = sum(q.values()); re = False
            if chosen != "Keep timing" and pre is not None and tot >= pre * .98:
                ban[chosen] = t + 8; re = True
            costs = {k: cost(q, t, sc, a, lam) for k, a in CANDS.items() if ban.get(k, -1) <= t}
            best = min(costs, key=costs.get)
            if best != "Keep timing" and costs[best] > .97 * costs["Keep timing"]: best = "Keep timing"
            sw += best != chosen and best != "Keep timing"
            log.append(dict(t=t * DT, chosen=best, reassess=re, failed=chosen if re else "",
                            costs={k: round(v, 1) for k, v in costs.items()}))
            chosen, pre = best, tot
        eff = {} if (ctrl == "gg" and inw(sc.get("fail"), t)) else CANDS[chosen] if ctrl == "gg" else {}
        step(q, t, sc, eff, ctrl, A[t], acc)
        hist.append(dict(q)); prev = hist[max(0, len(hist) - 4)]
        rk = {n: node_risk(q, prev, n) for n in NODES}
        tl["total"].append(round(sum(q.values()), 1)); tl["maxrisk"].append(round(max(rk.values()), 3))
        for n in NODES: tl["nodes"][n].append(round(rk[n], 3))
        mq = max(mq, max(q.values()))
    ends = [w[1] for w in (sc.get("block"), sc.get("sat")) if w]; rec = None
    if ends:
        e = max(ends); rec = next(((i - e) * DT for i in range(e, STEPS) if tl["maxrisk"][i] < .4), None)
    m = dict(avg_delay_s=acc["vs"] / max(acc["arr"], 1), max_queue=mq, throughput=acc["out"],
             spillback_events=acc["blk"], overflow=acc["over"], interventions=sw, recovery_s=rec)
    return m, tl, log

def run_all(name, seed=1, runs=5):
    sc = SCEN[name]; out = {}
    for key, ctrl in (("Fixed-time", "fixed"), ("Local queue-based", "local"), ("GRIDGUARD", "gg")):
        res = [run_one(ctrl, sc, seed + i) for i in range(runs)]
        mean = {k: (None if all(r[0][k] is None for r in res) else
                    round(float(np.mean([r[0][k] for r in res if r[0][k] is not None])), 1)) for k in res[0][0]}
        out[key] = dict(metrics=mean, timeline=res[0][1], log=res[0][2] if ctrl == "gg" else [])
    return dict(scenario=name, seed=seed, runs=runs, window=sc.get("block") or sc.get("sat"),
                fail=sc.get("fail"), steps=STEPS, dt=DT, results=out)
