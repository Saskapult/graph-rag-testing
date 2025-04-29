from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
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
	k: int = 5


db_url = os.getenv("DB_HOST", "neo4j://localhost:7687")
db_user = os.getenv("DB_USER", "neo4j")
db_pass = os.getenv("DB_PASSWORD", "no_password")
driver = GraphDatabase.driver(db_url, auth=(db_user, db_pass))
kg = KGGen(model=os.getenv("QUERY_MODEL", "openai/gpt-4o-mini"))

labels_cache = "graphs/kg_labels.json"
if not os.path.isfile(labels_cache):	
	print("Fetch graph...")
	graph = labels.nx_graph_neo4j(driver, refresh=True)
	print("Find communities...")
	data = labels.graph_communities(graph)
	print("Label communities...")
	labels.add_labels(data)
	storage.save_json(data, labels_cache)
data = storage.load_json(labels_cache)

app = FastAPI()


@app.get("/")
async def root():
	return {"message": "Hello World"}


@app.post("/query/")
async def query_thing(item: QueryItem):
	q = query.query_hack(item.question, kg, driver, k=item.k)

	entities = []
	for a, r, b in q["statements"]:
		entities.append(a)
		entities.append(b)
	entities = set(entities)

	paths = labels.label_paths_to(data, entities)
	dend = labels.data_dendrogram(paths)

	q["graph"] = nx.cytoscape_data(dend)

	return q


@app.get("/checkpoint/{checkpoint_id}")
async def get_checkpoint(checkpoint_id: str):
	# Basic santitization
	path = "./graphs/fema_tags/" + checkpoint_id.split("/")[-1]

	if os.path.isfile(path):
		data = storage.load_json(path)
		return data
	else:
		raise HTTPException(status_code=404, detail="Checkpoint not found")


@app.get("/input/{input_id}")
async def get_input(input_id: str):
	# Basic santitization
	path = "./inputs/" + input_id.split("/")[-1]

	if os.path.isfile(path):
		return FileResponse(path)
	else:
		raise HTTPException(status_code=404, detail="Input not found")


# Returns the dendrogram at this label, or just the root
# Does not account for nodes with a shared label
# 127.0.0.1:8000/label/Emergency%20Preparedness
# Maybe switch to another method without %20?
@app.get("/label/{label}")
async def get_label(label: str):
	if label == "root":
		return data
	if tree := labels.find_label(data, label):
		return tree
	else:
		raise HTTPException(status_code=404, detail="Label not found")


# @app.post("/input/")
# async def create_input(file: UploadFile):
