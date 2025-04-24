from kg_gen import KGGen, Graph
from pypdf import PdfReader
import storage
import argparse
import os
import time
from neo4j import GraphDatabase
import dspy
from dspy.utils.callback import BaseCallback
from pprint import pprint
import age
import json
import hashlib


db_url = os.getenv("DB_HOST", "neo4j://localhost:7687")
db_user = os.getenv("DB_USER", "neo4j")
db_pass = os.getenv("DB_PASSWORD", "no_password")
db_base = os.getenv("DB_DATABASE", "neo4j")

processing_model = os.getenv("PROCESSING_MODEL", "ollama/phi4")


def get_pdf_pages_text(path):
	reader = PdfReader(path)
	return [page.extract_text() for page in reader.pages]


# Creates collections of words, returns them and the page range they were pulled from
def make_pages_chunks(pages, chunk_size=100, spillover=10):
	# The number of words passed at the end of a page
	page_position = []
	cur_count = 0
	for i, page_text in enumerate(pages):
		words = page_text.split()
		cur_count += len(words)
		page_position.append(cur_count)

	# Collect (chunk, (st, en))
	chunks_sources = []
	words = [word for page in pages for word in page.split()]
	i = 0
	while True:
		segment = words[i:(i+chunk_size)]

		def find_page(word_i):
			page = 0
			while page_position[page] <= word_i:
				page += 1
				if page >= len(page_position):
					break
			return page

		st = find_page(i) 
		en = find_page(i + len(segment))

		# Splitting by words does lose whitespace information
		# Impact unknown 
		chunks_sources.append((
			" ".join(segment), 
			(st, en)
		))

		i += len(segment)
		if i < len(words):
			i -= spillover
		else:
			break

	return chunks_sources


def pdf_chunks(path):
	print(f"Reading pdf from {path}")
	pages = get_pdf_pages_text(path)
	chunks = make_pages_chunks(pages)
	print(f"Made {len(chunks)} chunks")
	formatted_chunks = []
	for i, text, (st, en) in enumerate(chunks):
		text_hash = hashlib.md5(text.encode()).hexdigest()
		formatted_chunks.append({
			"text": text,
			"hash": text_hash, # Used for stored filename
			# These are included in the graph as relationship properties
			"tags": {
				"document": path,
				"page_st": st,
				"page_en": en,
				"chunk_i": i,
				"checkpoint": f"chunk-{text_hash}.json",
				# "audio_timestamp": idk,
			}	
		})
	return formatted_chunks


# Looks for files with names in the chunk format, aggregates them, saves the 
# aggregated knowledge graph 
def aggregate_chunks(kg, chunks_dir):
	aggregation_fname = chunks_dir + "/aggregated.json"
	if os.path.isfile(aggregation_fname):
		print("Aggregation file already exists!")
		return

	graphs = []
	for fname in os.listdir(chunks_dir):
		if fname.startswith("chunk-"):
			print(f"Loading chunk graph '{fname}'")
			g = storage.load_chunk(chunks_dir + "/" + fname)["graph"]
			graphs.append(g)

	print(f"Aggregating {len(graphs)} graphs")

	aggregate_st = time.time()
	aggregated_graph = kg.aggregate(graphs)
	aggregate_en = time.time()
	aggregate_duration = aggregate_en - aggregate_st
	print(f"\tAggregation processed in {aggregate_duration:.2f}s")

	storage.save_graph(aggregated_graph, aggregation_fname)


# Processes a document and outputs chunk and aggregated data
# Does not aggregate them! 
def process_chunks(chunks, output_path, kg, limit=None, partial=None, skip_errors=True, checkpointing=True):
	n_processed = 0
	for i, chunk in enumerate(chunks):
		# Early termination option for testing
		if limit and i >= int(limit):
			print(f"Stopping chunk processing - limit {limit} chunks")
			break
		
		if partial and n_processed >= int(partial):
			print(f"Stopping chunk processing - partial {partial} chunks")
			break

		print(f"Process chunk {i+1}/{len(chunks)}")

		# Check for checkpoint
		chunk_output_path = output_path + "/" + chunk["tags"]["checkpoint"]
		if checkpointing and os.path.isfile(chunk_output_path):
			old_chunk = storage.load_json(chunk_output_path)
			if old_chunk["text"] != chunk["text"]:
				print("\tTODO: collision detection")
				exit(1)
			elif (not skip_errors) and "errors" in old_chunk.keys():
				print("\tReprocess error chunk")
			else:
				print("\tSkipping due to checkpoint detection!")
				continue

		kgraph = None
		errors = None
		try:
			generate_st = time.time()
			kgraph = kg.generate(
				input_data=chunk["text"],
			)
			generate_en = time.time()
			generate_duration = generate_en - generate_st
			# Timing output doesn't currently use chunking
			# Could append to a json file in the future 
			print(f"\tChunk processed in {generate_duration:.2f}s")
			chunk["time"] = generate_duration
			chunk["graph"] = kgraph
		except Exception as e:
			print(f"Generic error ({type(e)})")
			print("DSPY history:")
			dspy.inspect_history(n=1)
			if skip_errors:
				print(str(e))
			else:
				raise e
			print("\tError during kg-gen call, using dummy graph")
			chunk["errors"] = str(e)
			chunk["graph"] = Graph(
				entities = set({}),
				relations = set({}),
				edges = set({}),
			)

		print(f"\tSaving as '{chunk_output_path}'")
		storage.save_chunk(chunk, chunk_output_path)
		n_processed += 1


def make_relationships(chunks):
	# Dict of relation -> [tags]
	relation_sources = {}
	for chunk in chunks:
		for relation in chunk["graph"].relations:
			if relation in relation_sources:
				relation_sources[relation].append(chunk["tags"])
			else:
				relation_sources[relation] = [chunk["tags"]]
	return relation_sources


def write_graph_to_database(graph, relationships, driver):
	for i, entity in enumerate(graph.entities):
		print(f"Write entity {i+1}/{len(graph.entities)}")
		driver.execute_query(
			"CREATE (:Entity {id: $id})",
			id=entity,
			database_=db_base,
		)
	
	for i, ((a, r, b), tags) in enumerate(relationships.items()):
		print(f"Write relation {i+1}/{len(relationships)} ({a} ~ {r} ~ {b})")
		relation = storage.to_neo4j_repr(r)
		driver.execute_query(
			"MATCH (a:Entity {id: $id_a})" +
			"MATCH (b:Entity {id: $id_b})" + 
			f"CREATE (a)-[:{relation} {{ tags: $tags }}]->(b)",
			id_a=a,
			id_b=b,
			tags=json.dumps(tags),
			relation=relation,
			database_=db_base,
		)


def write_graph_to_database_psql(graph, relationships, ag):
	for i, entity in enumerate(graph.entities):
		print(f"Write entity {i+1}/{len(graph.entities)}")
		ag.execCypher("""
			CREATE (:Entity {id: %s})
		""", params=(storage.to_neo4j_repr(entity),))
	
	for i, ((a, r, b), tags) in enumerate(relationships.items()):
		print(f"Write relation {i+1}/{len(relationships)} ({a} ~ {r} ~ {b})")
		relation = storage.to_neo4j_repr(r)
		# We need to insert the relation name manually so that psycopg doesn't 
		# think it's a string
		ag.execCypher(f"""
			MATCH (a:Entity {{id: %s}})
			MATCH (b:Entity {{id: %s}})
			CREATE (a)-[:{relation} {{ tags: %s }}]->(b)
		""", params=(storage.to_neo4j_repr(a), storage.to_neo4j_repr(b), json.dumps(tags)))


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("filename")
	parser.add_argument("-o", "--output")
	parser.add_argument("-a", "--aggregate", action="store_true")
	parser.add_argument("-u", "--upload", action="store_true")
	parser.add_argument("--limit", help="only process up to n chunks")
	parser.add_argument("--partial", help="process n unprocessed chunks and then exit")
	parser.add_argument("--skiperrors", action="store_true")
	parser.add_argument("--only", help="process only chunk i, then output dspy history")
	parser.add_argument('--chunksize', default=100, type=int)
	parser.add_argument('--chunkoverlap', default=10, type=int)
	parser.add_argument("--postgres", action="store_true")
	args = parser.parse_args()

	kg = KGGen(
		model=processing_model,
	)

	os.makedirs(args.output, exist_ok=True)

	dspy.enable_logging()
	dspy.enable_litellm_logging()

	chunks = pdf_chunks(args.filename)

	if args.only:
		chunks = [chunks[int(args.only)]]
		process_chunks(chunks, args.output, kg, args.limit, args.partial, args.skiperrors, True)
		dspy.inspect_history(n=1)
	else:
		process_chunks(chunks, args.output, kg, args.limit, args.partial, args.skiperrors)

	if args.aggregate:
		print("Aggregating chunks")
		aggregate_chunks(kg, args.output)
	
	if args.upload:
		print("Collecting upload")
		chunks = [storage.load_chunk(f"{args.output}/{f}") for f in os.listdir(args.output) if f.startswith("chunk-")]
		relationships = make_relationships(chunks)
		aggregated_graph = storage.load_graph(f"{args.output}/aggregated.json")

		print("Uploading graph")
		if not args.postgres:
			print("(to neo4j)")
			with GraphDatabase.driver(db_url, auth=(db_user, db_pass)) as driver:
				driver.verify_connectivity()
				driver.execute_query(
					"MATCH (n) DETACH DELETE n",
					database_=db_base,
				)
				write_graph_to_database(aggregated_graph, relationships, driver)
		else:
			print("(to postgres)")
			ag = age.connect(
				dbname=db_base,
				user=db_user,
				password=db_pass,
				host="".join(db_url.split(":")[:-1]),
				port=db_url.split(":")[-1],
				graph="my_graph",
			)
			# We could just delete the graph here
			ag.execCypher("MATCH (n) DETACH DELETE n")
			write_graph_to_database_psql(aggregated_graph, relationships, ag)
			ag.commit()

	print("Done!")


if __name__ == "__main__":
	main()
