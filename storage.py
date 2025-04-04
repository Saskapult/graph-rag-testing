import json
from kg_gen import Graph
import os
from ast import literal_eval


def graph_to_json(graph):
	data = {
		"entities": list(graph.entities),
		"edges": list(graph.edges),
		"relations": list(graph.relations),
	}
	return data


def graph_from_json(data):
	graph = Graph(
		entities = data["entities"],
		relations = data["relations"],
		edges = data["edges"],
	)
	return graph


def save_json(data, path):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w") as f:
		json.dump(data, f, indent=2)


def load_json(path):
	data = None
	with open(path, "r") as f:
		data = json.load(f)
	return data


def save_graph(graph, path):
	data = graph_to_json(graph)
	save_json(data, path)


def load_graph(path):
	return graph_from_json(load_json(path))


def save_index(index, path):
	new_index = {str(k): str(v) for k, v in index.items()}
	save_json(new_index, path)


def load_index(path):
	old_index = load_json(path)
	new_index = {literal_eval(k): literal_eval(v) for k, v, in old_index.items()}
	return new_index
