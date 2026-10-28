"""Risk-level suggestions to avoid traffic. Advice only: nothing here controls real signals."""
import networkx as nx

def route_advice(risks, edges):
    g = nx.DiGraph(); [g.add_edge(u, v, weight=1 + risks[v] / 10, hop=1) for u, v, _ in edges]
    safe, direct = nx.shortest_path(g, "J1", "J5", weight="weight"), nx.shortest_path(g, "J1", "J5", weight="hop")
    return dict(safe=safe, direct=direct, differs=safe != direct)

def advise(R, comp, risks, edges):
    lvl = "high" if R >= .70 else "medium" if R >= .40 else "low"; worst = max(risks, key=risks.get); ops, trv = [], []
    if lvl == "low":
        ops = ["Keep the current signal plan.", "Keep watching: risk is below 0.40."]; trv = ["Normal travel. No need to change route or time."]
        head = "Traffic is flowing"
    else:
        if comp["Q"] >= .5: ops.append("Queue is long: lengthen green on the busiest approach by 10 to 15 s. Test it in the Intervention lab first.")
        if comp["G"] >= .4: ops.append("Queue is growing fast: act now, before it reaches the next junction.")
        if comp["D"] >= .4: ops.append(f"Downstream is filling: hold releases into {worst} so it can clear.")
        if comp["O"] >= .5: ops.append("Road space is mostly full: limit new vehicles entering this approach.")
        if not ops: ops.append("Several signals are rising together: recheck in a minute.")
        ops.append(f"Watch {worst} first. It has the highest cascade risk ({risks[worst]:.0f}/100).")
        trv = ["Expect delays on this corridor.", "Leave earlier or delay non-urgent trips."]; head = "Congestion is building"
        if lvl == "high":
            head = "Gridlock risk is high"
            ops += ["Send traffic staff to the bottleneck if possible.", "Keep one lane clear for emergency vehicles.",
                    "Re-measure after each change. If risk does not fall, try the next action."]
            trv = ["Avoid this corridor now.", "Delay non-urgent trips by 20 to 30 minutes."]
    ra = route_advice(risks, edges)
    if lvl != "low" and ra["differs"]: trv.append("Lower-risk route: " + " to ".join(ra["safe"]) + ".")
    return dict(level=lvl, headline=head, operator=ops, travellers=trv, route=ra, note="Advice only. This app does not control real traffic lights.")
