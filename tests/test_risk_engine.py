from risk_engine import calculate_risk, risk_label
from cascade_analysis import build_intersection_graph, propagate_cascade_risk
from intervention import compare_interventions

def test_risk_is_bounded():
    assert 0 <= calculate_risk(5, .05, 2, 4, .2) <= 100

def test_labels():
    assert risk_label(10) == "LOW"
    assert risk_label(50) == "MEDIUM"
    assert risk_label(80) == "HIGH"

def test_graph():
    graph = build_intersection_graph()
    assert len(graph.nodes) == 5
    assert all(0 <= v <= 100 for v in propagate_cascade_risk(graph, {"J1": 90}).values())

def test_interventions():
    choices = compare_interventions({"risk": 80, "vehicle_count": 20, "occupancy": .3, "queue_proxy": 10})
    assert len(choices) >= 3

def test_advisor():
    from advisor import advise
    risks = {"J1": 80, "J2": 60, "J3": 40, "J4": 10, "J5": 5}
    edges = [["J1","J2",.7],["J2","J3",.65],["J2","J4",.45],["J3","J5",.6],["J4","J3",.3]]
    comp = {"Q": .8, "O": .6, "G": .5, "D": .5}
    assert advise(.8, comp, risks, edges)["level"] == "high"
    assert advise(.2, comp, risks, edges)["level"] == "low"
