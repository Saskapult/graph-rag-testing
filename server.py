from fastapi import FastAPI
import query
from pydantic import BaseModel
import os
from neo4j import GraphDatabase
from kg_gen import KGGen
import labels
import storage


class QueryItem(BaseModel):
	question: str


db_url = os.getenv("DB_HOST", "neo4j://localhost:7687")
db_user = os.getenv("DB_USER", "neo4j")
db_pass = os.getenv("DB_PASSWORD", "no_password")
driver = GraphDatabase.driver(db_url, auth=(db_user, db_pass))
kg = KGGen(model=os.getenv("QUERY_MODEL", "openai/gpt-4o-mini"))

labels_cache = "/tmp/labels.json"
graph_labels = None
print("Fetch graph...")
graph = labels.nx_graph_neo4j(driver)
print("Find communities...")
community = labels.graph_communities(graph) # takes ages

if not os.path.isfile(labels_cache):	
	calls, tokens = labels.communities_label_count(community)
	token_cost = 1.100 / 1e6
	print(f"Labelling will make {calls} calls with {tokens} input tokens ({tokens*token_cost}$)")
	input("Continue?")
	graph_labels = labels.label_communities(graph, community)
	storage.save_json(graph_labels, labels_cache)
else:
	print("Load labels from cache")
	graph_labels = storage.load_json(labels_cache)
dendro = labels.nx_graph_labels(graph_labels)

# print(graph_labels)
# print(list(graph.nodes(data="id"))[:20])
# assert "FEMA" in list(graph.nodes(data="id"))
community = labels.map_communities_to_node_data(graph, community)
g = labels.label_path_to(graph, community, graph_labels, "FEMA")
print(g)
print("Done")
g2 = labels.nx_graph_labels(g)
print("Draw")
labels.draw_circle_graph_thing(g2)

# query.query_hack("How is FEMA related to NIMS?", kg, driver, k=5)

exit(0)

app = FastAPI()


@app.get("/")
async def root():
	return {"message": "Hello World"}


@app.post("/query/")
async def query_thing(item: QueryItem):
	return query.query_hack(item.question, kg, driver, k=5)


# def main():
# 	kg = KGGen(
# 		model=processing_model,
# 	)


# if __name == "__main__":
# 	main()
