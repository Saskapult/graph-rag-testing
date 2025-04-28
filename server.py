from fastapi import FastAPI
import query
from pydantic import BaseModel
import os
from neo4j import GraphDatabase
from kg_gen import KGGen
import labels
import storage
import networkx as nx


class QueryItem(BaseModel):
	question: str


db_url = os.getenv("DB_HOST", "neo4j://localhost:7687")
db_user = os.getenv("DB_USER", "neo4j")
db_pass = os.getenv("DB_PASSWORD", "no_password")
driver = GraphDatabase.driver(db_url, auth=(db_user, db_pass))
kg = KGGen(model=os.getenv("QUERY_MODEL", "openai/gpt-4o-mini"))

labels_cache = "/tmp/labels2.json"
if not os.path.isfile(labels_cache):	
	print("Fetch graph...")
	graph = labels.nx_graph_neo4j(driver, refresh=True)
	print("Find communities...")
	data = labels.graph_communities(graph)
	print("Label communities...")
	labels.add_labels(data)
	storage.save_json(data, labels_cache)
data = storage.load_json(labels_cache)

# print("Path...")
# # path = labels.label_path_to(data, "FEMA")
# # TODO: Case insensitive 
# path = labels.label_paths_to(data, ["FEMA", "NIMS"])
# print(path)

# dend = labels.data_dendrogram(path)
# # labels.draw_circle_graph_thing(dend)
# print(nx.cytoscape_data(dend))
# print(type(nx.cytoscape_data(dend)))


# exit(0)

# # community = labels.graph_communities(graph) # takes ages
# graph_labels = None
# # 	calls, tokens = labels.communities_label_count(community)
# # 	token_cost = 1.100 / 1e6
# # 	print(f"Labelling will make {calls} calls with {tokens} input tokens ({tokens*token_cost}$)")
# # 	input("Continue?")
# # 	graph_labels = labels.label_communities(graph, community)
# # 	storage.save_json(graph_labels, labels_cache)
# # else:
# # 	print("Load labels from cache")
# # dendro = labels.nx_graph_labels(graph_labels)

# # print(graph_labels)
# # print(list(graph.nodes(data="id"))[:20])
# # assert "FEMA" in list(graph.nodes(data="id"))
# community = labels.map_communities_to_node_data(graph, community)
# g = labels.label_path_to(graph, community, graph_labels, "FEMA")
# print(g)
# print("Done")
# g2 = labels.nx_graph_labels(g)
# print("Draw")
# labels.draw_circle_graph_thing(g2)

# # query.query_hack("How is FEMA related to NIMS?", kg, driver, k=5)

# exit(0)

app = FastAPI()


@app.get("/")
async def root():
	return {"message": "Hello World"}


@app.post("/query/")
async def query_thing(item: QueryItem):
	q = query.query_hack(item.question, kg, driver, k=5)

	entities = []
	for a, r, b in q["statements"]:
		entities.append(a)
		entities.append(b)
	entities = set(entities)

	paths = labels.label_paths_to(data, entities)
	dend = labels.data_dendrogram(paths)

	q["graph"] = nx.cytoscape_data(dend)

	return q
