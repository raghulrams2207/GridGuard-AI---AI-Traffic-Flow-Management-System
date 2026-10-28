"""Real SUMO + TraCI evaluation on a 3x2 signalised grid (6 junctions, simulation/grid.net.xml).
Compares fixed-time, local queue-based and GRIDGUARD (downstream-aware, counterfactual via saveState/loadState,
closed-loop reassessment) on identical demand and seeds. Results are SUMO measurements, not real-world claims."""
import tempfile, threading
from pathlib import Path
import numpy as np, sumolib, traci

NET = Path(__file__).parent / "simulation" / "grid.net.xml"
END, DT, STEPS, LOCK = 1200, 10, 120, threading.Lock()
FLOWS = [("left0A0", "C0right0", 1), ("left1A1", "C1right1", 1), ("right0C0", "A0left0", 1), ("right1C1", "A1left1", 1),
         ("bottom0A0", "A1top0", .5), ("bottom1B0", "B1top1", .5), ("bottom2C0", "C1top2", .5), ("top1B1", "B0bottom1", .5)]
SCEN = {"normal": dict(vph=350), "peak": dict(vph=1100), "blockage": dict(vph=850, block=(300, 700)),
        "saturation": dict(vph=950, sat=(300, 800)), "failure": dict(vph=850, block=(300, 700), fail=(350, 700))}
BLOCK, SAT = ["B0C0"], ["C0right0", "C1right1"]
CANDS = ["Keep timing", "A: extend green", "B: protect downstream", "C: adaptive rerouting"]
clamp = lambda v: max(0.0, min(1.0, float(v)))
inw = lambda w, t: bool(w) and w[0] <= t < w[1]
lanes_of = lambda edges: [l for e in edges for l in (f"{e}_{i}" for i in range(traci.edge.getLaneNumber(e)))]

def tls_info():
    info = {}
    for t in traci.trafficlight.getIDList():
        links = traci.trafficlight.getControlledLinks(t); lg = traci.trafficlight.getAllProgramLogics(t)[0]; ph = []
        for i, p in enumerate(lg.phases):
            g = [k for k, c in enumerate(p.state) if c in "Gg" and links[k]]
            if g: ph.append((i, sorted({links[k][0][0] for k in g}), sorted({links[k][0][1] for k in g})))
        info[t] = dict(lg=lg, ph=ph, base={i: p.duration for i, p in enumerate(lg.phases)},
                       inl=sorted({l[0][0] for l in links if l}), out=sorted({l[0][1] for l in links if l}))
    return info

def durations(info, t, act):
    sc = [(sum(traci.lane.getLastStepHaltingNumber(l) for l in a), i, max(traci.lane.getLastStepOccupancy(l) for l in b))
          for i, a, b in info[t]["ph"]]
    d = {}
    if not sc: return d
    top = max(sc)[1]
    for h, i, oc in sc:
        b = info[t]["base"][i]
        if act == "A: extend green" and i == top: d[i] = min(b + 15, 60)
        elif act == "B: protect downstream":
            if oc > 50: d[i] = max(6, b * .5)
            elif i == top: d[i] = min(b + 10, 55)
        elif act == "local": d[i] = min(45, max(10, 10 + 3 * h))
    return d

def apply_all(info, act):
    for t in info:
        lg = info[t]["lg"]; d = durations(info, t, act)
        ph = [traci.trafficlight.Phase(d.get(i, p.duration), p.state) for i, p in enumerate(lg.phases)]
        traci.trafficlight.setProgramLogic(t, traci.trafficlight.Logic(lg.programID, lg.type, traci.trafficlight.getPhase(t), ph))

def advance(sec, reroute, allin):
    q, spill = [], 0
    for k in range(sec):
        traci.simulationStep()
        if reroute and k % 20 == 0:
            for v in traci.vehicle.getIDList(): traci.vehicle.rerouteTraveltime(v)
        if k % 5 == 0:
            q.append(sum(traci.lane.getLastStepHaltingNumber(l) for l in allin))
            spill += sum(traci.lane.getLastStepOccupancy(l) > 60 for l in allin)
    worst = max(traci.lane.getLastStepHaltingNumber(l) for l in allin)
    return .4 * float(np.mean(q)) + .3 * worst + .2 * spill + .5 * len(traci.simulation.getPendingVehicles())

def run_one(ctrl, sc, seed, d):
    rows = ['<routes><vType id="c" accel="2.6" decel="4.5" sigma="0.5" length="5" maxSpeed="14"/>']
    rows += [f'<flow id="f{i}" type="c" begin="0" end="{END - 120}" from="{a}" to="{b}" probability="{sc["vph"] * m / 3600:.5f}" departLane="best" departSpeed="max"/>' for i, (a, b, m) in enumerate(FLOWS)]
    rf, sf = Path(d) / "r.rou.xml", str(Path(d) / "s.xml")
    rf.write_text("\n".join(rows + ["</routes>"]))
    traci.start([sumolib.checkBinary("sumo"), "-n", str(NET), "-r", str(rf), "--seed", str(seed), "--no-step-log", "--no-warnings",
                 "--time-to-teleport", "300"])
    try:
        info = tls_info(); allin = sorted({l for t in info.values() for l in t["inl"]})
        bl, st = lanes_of(BLOCK), lanes_of(SAT); spd = {l: traci.lane.getMaxSpeed(l) for l in bl + st}
        chosen, pre, ban, sw, reroute, tele, mq, spill = "Keep timing", None, {}, 0, False, 0, 0, 0
        cache, tli = {}, []
        tl = dict(total=[], maxrisk=[], nodes={t: [] for t in info}); log = []; hh = []
        for s in range(STEPS):
            t = s * DT
            if sc.get("block") and t in (sc["block"][0], sc["block"][1]):
                for l in bl: traci.lane.setMaxSpeed(l, .3 if t == sc["block"][0] else spd[l])
            if sc.get("sat") and t in (sc["sat"][0], sc["sat"][1]):
                for l in st: traci.lane.setMaxSpeed(l, 1.5 if t == sc["sat"][0] else spd[l])
            if ctrl == "local" and t % 30 == 0: apply_all(info, "local")
            if ctrl == "gg" and t % 60 == 0 and t > 0:
                tot = sum(traci.lane.getLastStepHaltingNumber(l) for l in allin); re = False
                if chosen != "Keep timing" and pre is not None and tot >= pre * .98: ban[chosen] = t + 180; re = True
                costs = {}; traci.simulation.saveState(sf)
                for c in CANDS:
                    if ban.get(c, -1) > t: continue
                    apply_all(info, c); costs[c] = advance(40, c == CANDS[3], allin); traci.simulation.loadState(sf)
                best = min(costs, key=costs.get)
                if best != "Keep timing" and costs[best] > .97 * costs["Keep timing"]: best = "Keep timing"
                sw += best != chosen and best != "Keep timing"
                log.append(dict(t=t, chosen=best, reassess=re, failed=chosen if re else "", costs={k: round(v, 1) for k, v in costs.items()}))
                chosen, pre = best, tot
                eff = "Keep timing" if inw(sc.get("fail"), t) else chosen
                apply_all(info, eff); reroute = eff == CANDS[3]
            for k in range(DT):
                for v in traci.vehicle.getIDList(): cache[v] = traci.vehicle.getTimeLoss(v)
                traci.simulationStep(); tli += [cache.pop(v, 0.0) for v in traci.simulation.getArrivedIDList()]; tele += traci.simulation.getStartingTeleportNumber()
                if reroute and k % 20 == 0:
                    for v in traci.vehicle.getIDList(): traci.vehicle.rerouteTraveltime(v)
            rk, tot = {}, 0; hh.append({})
            for n, i in info.items():
                H = sum(traci.lane.getLastStepHaltingNumber(l) for l in i["inl"]); hh[-1][n] = H; tot += H; mq = max(mq, H)
                occ = np.mean([traci.lane.getLastStepOccupancy(l) for l in i["inl"]]); od = max(traci.lane.getLastStepOccupancy(l) for l in i["out"])
                G = clamp((H - hh[max(0, len(hh) - 4)][n]) / 8)
                rk[n] = .35 * clamp(H / (len(i["inl"]) * 6)) + .25 * clamp(occ / 50) + .2 * G + .2 * clamp(od / 60)
            spill += sum(traci.lane.getLastStepOccupancy(l) > 60 for l in allin)
            tl["total"].append(tot); tl["maxrisk"].append(round(max(rk.values()), 3))
            for n in info: tl["nodes"][n].append(round(rk[n], 3))
        pend = len(traci.simulation.getPendingVehicles()); rem = [traci.vehicle.getTimeLoss(v) for v in traci.vehicle.getIDList()]
    finally: traci.close()
    ends = [w[1] for w in (sc.get("block"), sc.get("sat")) if w]; rec = None
    if ends:
        e = max(ends) // DT; rec = next(((i - e) * DT for i in range(e, STEPS) if tl["maxrisk"][i] < .4), None)
    m = dict(avg_delay_s=(sum(tli) + sum(rem)) / max(len(tli) + len(rem), 1), max_queue=mq, throughput=len(tli),
             spillback_events=spill, overflow=pend + tele, interventions=sw, recovery_s=rec)
    return m, tl, log

def run_all(name, seed=1, runs=3):
    sc, out = SCEN[name], {}
    with LOCK, tempfile.TemporaryDirectory() as d:
        for key, ctrl in (("Fixed-time", "fixed"), ("Local queue-based", "local"), ("GRIDGUARD", "gg")):
            res = [run_one(ctrl, sc, seed + i, d) for i in range(runs)]
            mean = {k: (None if all(r[0][k] is None for r in res) else round(float(np.mean([r[0][k] for r in res if r[0][k] is not None])), 1)) for k in res[0][0]}
            out[key] = dict(metrics=mean, timeline=res[0][1], log=res[0][2] if ctrl == "gg" else [])
    w = sc.get("block") or sc.get("sat"); f = sc.get("fail")
    return dict(scenario=name, seed=seed, runs=runs, window=w and [w[0] // DT, w[1] // DT], fail=f and [f[0] // DT, f[1] // DT],
                steps=STEPS, dt=DT, engine="SUMO + TraCI, 3x2 signalised grid (6 junctions)", results=out)
