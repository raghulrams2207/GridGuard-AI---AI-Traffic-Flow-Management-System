"""Illustrative graph model for cascading congestion risk."""
import networkx as nx

def build_intersection_graph():
    graph = nx.DiGraph()
    graph.add_nodes_from(["J1", "J2", "J3", "J4", "J5"])
    graph.add_edge("J1", "J2", weight=0.70)
    graph.add_edge("J2", "J3", weight=0.65)
    graph.add_edge("J2", "J4", weight=0.45)
    graph.add_edge("J3", "J5", weight=0.60)
    graph.add_edge("J4", "J3", weight=0.30)
    return graph

def propagate_cascade_risk(graph, initial_risks, attenuation=0.55, iterations=4):
    risks = {
        node: max(0.0, min(100.0, float(initial_risks.get(node, 10.0))))
        for node in graph.nodes()
    }
    for _ in range(iterations):
        updated = dict(risks)
        for source, target, data in graph.edges(data=True):
            propagated = risks[source] * float(data.get("weight", 0.5)) * attenuation
            updated[target] = max(updated[target], propagated)
        risks = {node: min(100.0, score) for node, score in updated.items()}
    return risks
