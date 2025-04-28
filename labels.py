import neo4j
import networkx as nx
import itertools

db_url = os.getenv("DB_HOST", "neo4j://localhost:7687")
db_user = os.getenv("DB_USER", "neo4j")
db_pass = os.getenv("DB_PASSWORD", "no_password")
db_base = os.getenv("DB_DATABASE", "neo4j")
label_model = os.getenv("LABEL_MODEL", "openai/gpt-4o-mini")


# Pulls an entire neo4j database and makes a networkx graph from it
def nx_graph_neo4j(driver):
	export_temp = "/tmp/communities_neo4j_export.graphml"

	if not os.path.isfile(export_temp):
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
def graph_communities(
	graph,
	# Any commmunity with more than this many nodes will be further divided
	subdivision_threshold=8, 
	# Communities (try to) split into at most this many subcommunities 
	branchiness=6,
):
	comp = nx.community.girvan_newman(graph)

	communities = next(comp)
	# print(f"Split into {len(communities)} communities")
	# assert False
	result = []
	for community in communities:
		if len(community) > subdivision_threshold:
			# print("Split interior community")
			subgraph = graph.subgraph(community)
			result.append(graph_communities(subgraph))
		else:
			# print("Reached leaf community")
			result.append(community)
	return result


# Finds how many calls we will make to label a community set
# Returns number of calls, number of tokens in those calls
# Tokens are assumed to be words, punctuation is not counted 
# Also does not account for output token cost
def communities_label_count(communities):
	if isinstance(communities, list) or isinstance(communities, set):
		calls = 0
		tokens = 0
		for community in communities:
			c_calls, c_tokens = communities_label_count(community)
			calls += c_calls
			tokens += c_tokens
		return calls, tokens
	else:
		assert isinstance(communities, str)
		return 1, len(communities.split())


class CommunityLabelSignature(dspy.Signature):
	"""
	Given a collection of entities, find a few words to label them.
	"""
	entities: list[str] = dspy.InputField()
	label: str = dspy.OutputField()	


_label_community_p = dspy.Predict(CommunityLabelSignature)


def _label_entities(entities):
	return _label_community_p(entities=entities).label


def _label_community(graph, community):
	return label_entities([l for n, l in graph.subgraph(community).nodes(data="id")])


def _label_communities(graph, communities):
	if isinstance(communities, list):
		inner = [label_communities(graph, c) for c in communities]
		labels, _ = zip(*inner)
		# print(f"Make label for {labels}")
		return (_label_entities(labels), inner)
	else:
		# print(f"Make terminal label for {communities}")
		# Temrinal is a set
		assert isinstance(communities, set)
		return (_label_community(graph, list(communities)), [])


# Generates labels for a collection of communities 
# Estimate the cost with communities_label_count
def label_communities(graph, communities):
	with dspy.context(lm=dspy.LM(label_model)):
		return _label_communities(graph, communities)


def _dfs_node_addition(graph, labels, parent):
	root, children = labels
	graph.add_node(root)
	if parent:
		graph.add_edge(parent, root)
		# print(f"{parent} -> {root}")
	
	for label in children:
		dfs_node_addition(graph, label, root)


# Creates a dendrogram of labels in the form of a networkx graph 
# TODO: Fix the issue of nodes with identical named being merged 
def nx_graph_labels(labels):
	graph = nx.Graph()
	_dfs_node_addition(
		graph,
		labels,
		None,
	)
	return graph
