"""Heuristic intervention comparison; not calibrated predictions or SUMO results."""
def compare_interventions(current):
    risk = max(0.0, min(100.0, float(current.get("risk", 20))))
    vehicles = max(0, int(current.get("vehicle_count", 0)))
    occupancy = max(0.0, min(1.0, float(current.get("occupancy", 0.0))))
    queue_proxy = max(0, int(current.get("queue_proxy", 0)))
    actions = [
        ("Maintain current timing", "Keep baseline signal plan", 0, 0, 0),
        ("Extend green on approach", "Illustrative green extension", min(22, 5+vehicles*.45), min(18, 4+queue_proxy*.65), 8 if occupancy>.25 else 2),
        ("Protect downstream capacity", "Avoid releasing into a saturated downstream link", min(28, 8+occupancy*45), min(12, 3+occupancy*25), 0),
        ("Coordinated corridor response", "Coordinate neighbors and reduce upstream release", min(32, 10+queue_proxy*.8), min(20, 5+vehicles*.55), 3),
    ]
    result = []
    for name, desc, reduction, delay, penalty in actions:
        after = max(0.0, risk * (1-reduction/100))
        result.append({
            "action": name, "description": desc,
            "risk_reduction_pct": round(reduction, 1),
            "delay_reduction_pct": round(delay, 1),
            "downstream_blockage_penalty": round(penalty, 1),
            "estimated_risk_after_action": round(after, 1),
            "estimated_objective_score": round(after+penalty, 1),
        })
    return result
