"""Transparent heuristic risk scoring. Scores are not calibrated probabilities."""
def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, float(value)))

def calculate_risk(vehicle_count, occupancy, queue_proxy, previous_count=0, downstream_risk=0.0):
    count_severity = _clamp(vehicle_count / 25.0)
    occupancy_severity = _clamp(occupancy / 0.30)
    queue_severity = _clamp(queue_proxy / 15.0)
    growth_severity = _clamp(max(0.0, float(vehicle_count) - float(previous_count)) / 8.0)
    downstream = _clamp(downstream_risk)
    score = (0.25*count_severity + 0.20*occupancy_severity + 0.20*queue_severity
             + 0.15*growth_severity + 0.20*downstream) * 100
    return round(max(0.0, min(100.0, score)), 1)

def risk_label(score):
    if float(score) >= 70: return "HIGH"
    if float(score) >= 35: return "MEDIUM"
    return "LOW"
