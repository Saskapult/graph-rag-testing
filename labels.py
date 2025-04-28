import neo4j
import networkx as nx
import itertools
import os
import dspy
from neo4j import GraphDatabase

db_url = os.getenv("DB_HOST", "neo4j://localhost:7687")
db_user = os.getenv("DB_USER", "neo4j")
db_pass = os.getenv("DB_PASSWORD", "no_password")
db_base = os.getenv("DB_DATABASE", "neo4j")
label_model = os.getenv("LABEL_MODEL", "openai/gpt-4o-mini")


# Pulls an entire neo4j database and makes a networkx graph from it
def nx_graph_neo4j(driver, refresh=False):
	export_temp = "/tmp/communities_neo4j_export.graphml"

	if refresh or not os.path.isfile(export_temp):
		print("Connecting to db")
		with GraphDatabase.driver(db_url, auth=(db_user, db_pass)) as driver:
			driver.verify_connectivity()

			print("Fetching database as graphml")
			records, _, _ = driver.execute_query("""
				CALL apoc.export.graphml.all(null, {stream:true})
				YIELD file, nodes, relationships, properties, data
				RETURN file, nodes, relationships, properties, data
			""")
			_, n_nodes, n_relationships, _, export_contents = records[0]
			print(f"Downloaded {n_nodes} nodes, {n_relationships} relationships")

			print("Saving as temporary file")
			with open(export_temp, "w") as f:
				f.write(export_contents)
	else:
		print("Loading cached database")
	
	graph = nx.read_graphml(export_temp)
	return graph


# Splits a graph into communities 
def _graph_communities(
	graph,
	# Any commmunity with more than this many nodes will be further divided
	subdivision_threshold=8, 
	# Communities (try to) split into at most this many subcommunities 
	branchiness=6,
):
	# comp = nx.community.girvan_newman(graph)
	# communities = next(comp)

	communities = nx.community.louvain_communities(graph)

	# print(f"Split into {len(communities)} communities")
	# assert False
	result = []
	for community in communities:
		if len(community) > subdivision_threshold:
			# print("Split interior community")
			subgraph = graph.subgraph(community)
			result.append(_graph_communities(subgraph))
		else:
			# print("Reached leaf community")
			result.append(community)
	return result


def _communities_data(graph, communities):
	if isinstance(communities, str):
		return {
			"index": communities,
			"id": graph.nodes[communities]["id"],
		}
	else:
		return {
			"children": [_communities_data(graph, c) for c in communities],
		}


def graph_communities(graph, **kwargs):
	print("Make communities")
	communities = _graph_communities(graph, **kwargs)
	print("Extract communities")
	data = _communities_data(graph, communities)
	return data



# Finds how many calls we will make to label a community set
# Returns number of calls, number of tokens in those calls
# Tokens are assumed to be words, punctuation is not counted 
# Also does not account for output token cost
def label_count(data):
	if "children" in data.keys():
		calls = 0
		tokens = 0
		for community in data["children"]:
			c_calls, c_tokens = communities_label_count(community)
			calls += c_calls
			tokens += c_tokens
		return calls, tokens
	else:
		return 1, len(data["id"].split())


class CommunityLabelSignature(dspy.Signature):
	"""
	Given a collection of entities, find a few words to label them.
	"""
	entities: list[str] = dspy.InputField()
	label: str = dspy.OutputField()	


_label_community_p = dspy.Predict(CommunityLabelSignature)


def _label_entities(entities):
	return _label_community_p(entities=entities).label


def _add_labels(data):
	if "children" in data.keys():
		for child in data["children"]:
			_add_labels(child)
		inner = [c["label"] for c in data["children"]]
		data["label"] = _label_entities([c["label"] for c in data["children"]])
	else:
		data["label"] = data["id"]


# Generates labels for a collection of communities 
# Estimate the cost with communities_label_count
def add_labels(data):
	with dspy.context(lm=dspy.LM(label_model)):
		return _add_labels(data)


def _dfs_node_addition(graph, data, parent):
	print(data)
	root = data["label"]
	graph.add_node(root)
	if parent:
		graph.add_edge(parent, root)
		# print(f"{parent} -> {root}")
	
	if "children" in data.keys():
		for c in data["children"]:
			_dfs_node_addition(graph, c, root)


# Creates a dendrogram of labels in the form of a networkx graph 
# TODO: Fix the issue of nodes with identical named being merged 
def data_dendrogram(data):
	graph = nx.Graph()
	_dfs_node_addition(
		graph, 
		data,
		None,
	)
	return graph


def label_path_to(data, entity):
	if "id" in data.keys():
		# Leaf
		if data["id"] == entity:
			return data
		else:
			return None
	else:
		for c in data["children"]:
			if path := label_path_to(c, entity):
				d = dict(data)
				d["children"] = [path]
				return d
		return None


def label_paths_to(data, entities):
	if "id" in data.keys():
		if data["id"] in entities:
			return data
		else:
			return None
	else:
		d = dict(data)
		d["children"] = []
		for c in data["children"]:
			if path := label_paths_to(c, entities):
				d["children"].append(path)
		if len(d["children"]) > 0:
			return d
		else:
			return None




import matplotlib.pyplot as plt
def draw_circle_graph_thing(graph):
	pos = nx.nx_agraph.graphviz_layout(graph, prog="twopi", args="")
	plt.figure(figsize=(8, 8))
	nx.draw(graph, pos, node_size=20, alpha=0.75, node_color="blue", with_labels=True, font_size=10)
	plt.axis("equal")
	plt.show()
