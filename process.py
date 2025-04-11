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


db_url = os.getenv("DB_HOST", "neo4j://localhost:7687")
db_user = os.getenv("DB_USER", "neo4j")
db_pass = os.getenv("DB_PASSWORD", "no_password")
db_base = os.getenv("DB_DATABASE", "neo4j")

processing_model = os.getenv("PROCESSING_MODEL", "ollama/phi4")


def get_pdf_pages_text(path):
	reader = PdfReader(path)
	return [page.extract_text() for page in reader.pages]


# Creates collections of words, returns them and the page range they were pulled from
def make_chunks(pages, chunk_size=100, spillover=10):
	# The number of words passed at the end of a page
	page_position = {}
	cur_count = 0
	for i, page_text in enumerate(pages):
		words = page_text.split()
		cur_count += len(words)
		page_position[i+1] = cur_count

	# Reverse to find page number by position
	position_page = [(v, k) for k, v in page_position.items()]
	position_page.sort()

	# Collect (chunk, (st, en))
	chunks_sources = []
	words = [word for page in pages for word in page.split()]
	i = 0
	while True:
		segment = words[i:(i+chunk_size)]
		
		st = 0
		en = len(pages)
		for position, page in position_page:
			if position > i:
				if position > i + chunk_size:
					en = page
					break
			else:
				st = page

		# Splitting by words does lose whitespace information
		# Impact unknown 
		chunks_sources.append((" ".join(segment), (st, en)))

		i += len(segment)
		if i < len(words):
			i -= spillover
		else:
			break

	return chunks_sources


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
def process_chunks(chunks, output_path, kg, limit=None, partial=None, skip_errors=True, skip_check=False):
	n_processed = 0
	for i, (entry, (st, en)) in enumerate(chunks):
		# Early termination option for testing
		if limit and i >= int(limit):
			print(f"Stopping chunk processing - limit {limit} chunks")
			break
			
		if partial and n_processed >= int(partial):
			print(f"Stopping chunk processing - partial {partial} chunks")
			break

		print(f"Process chunk {i+1}/{len(chunks)}")

		# Check for checkpoint
		chunk_output_path = output_path + f"/chunk-{i}-{st}-{en}.json"
		if (not skip_check) and os.path.isfile(chunk_output_path):
			print("\tSkipping due to checkpoint detection!")
			continue
		
		chunk_json = {
			"chunk_i": i,
			"source_text": entry,
			"page_st": st, 
			"page_en": en,
		}

		kgraph = None
		errors = None
		try:
			generate_st = time.time()
			kgraph = kg.generate(
				input_data=entry,
			)
			generate_en = time.time()
			generate_duration = generate_en - generate_st
			# Timing output doesn't currently use chunking
			# Could append to a json file in the future 
			print(f"\tChunk processed in {generate_duration:.2f}s")
			chunk_json["time"] = generate_duration
			chunk_json["kgraph"] = kgraph
		except Exception as e:
			print(f"Generic error ({type(e)})")
			print("DSPY history:")
			dspy.inspect_history(n=1)
			if skip_errors:
				print(str(e))
			else:
				raise e
			print("\tError during kg-gen call, using dummy graph")
			chunk_json["errors"] = str(e)
			chunk_json["kgraph"] = Graph(
				entities = set({}),
				relations = set({}),
				edges = set({}),
			)

		print(f"\tSaving as '{chunk_output_path}'")
		storage.save_chunk(chunk_json, chunk_output_path)
		n_processed += 1


# Reads chunk graphs to generate a source index
# You'll probably want to store this in a database 
def make_index(graphs_path):
	# Dict of relation -> (chunk n, page start, page end)
	relation_sources = {}
	for file in os.listdir(graphs_path):
		if file.startswith("chunk-"):
			_, n, st, en = file.split(".")[0].split("-")
			n = int(n)
			st = int(st)
			en = int(en)
			print(f"Chunk {n} sources pages {st} to {en}")
			graph = storage.load_chunk(graphs_path + "/" + file)["graph"]
			print(f"\t{len(graph.relations)} relations found")
			for relation in graph.relations:
				if relation in relation_sources:
					relation_sources[relation].append((n, st, en))
				else:
					relation_sources[relation] = [(n, st, en)]
	return relation_sources



def clear_database(driver):
	driver.execute_query(
		"MATCH (n) DETACH DELETE n",
		database_=db_base,
	)


def write_graph_to_database(graph, driver):
	print(f"Writing '{graph}' to database")

	for i, entity in enumerate(graph.entities):
		print(f"Write entity {i+1}/{len(graph.entities)}")
		driver.execute_query(
			"CREATE (:Entity {id: $id})",
			id=entity,
			database_=db_base,
		)
	
	for i, (a, r, b) in enumerate(graph.relations):
		print(f"Write relation {i+1}/{len(graph.relations)} ({a} ~ {r} ~ {b})")
		relation = storage.to_neo4j_repr(r)
		driver.execute_query(
			"MATCH (a:Entity {id: $id_a})" +
			"MATCH (b:Entity {id: $id_b})" + 
			f"CREATE (a)-[:{relation}]->(b)",
			id_a=a,
			id_b=b,
			relation=relation,
			database_=db_base,
		)


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("filename")
	parser.add_argument("-o", "--output")
	parser.add_argument("-a", "--aggregate", action="store_true")
	parser.add_argument("-i", "--index", action="store_true")
	parser.add_argument("-u", "--upload", action="store_true")
	parser.add_argument("--limit", help="only process up to n chunks")
	parser.add_argument("--partial", help="process n unprocessed chunks and then exit")
	parser.add_argument("--skiperrors", action="store_true")
	parser.add_argument("--only", help="process only chunk i, then output dspy history")
	args = parser.parse_args()

	kg = KGGen(
		model=processing_model,
	)

	os.makedirs(args.output, exist_ok=True)

	dspy.enable_logging()
	dspy.enable_litellm_logging()

	print(f"Reading text from {args.filename}")
	pages = get_pdf_pages_text(args.filename)
	print("Making chunks")
	chunks = make_chunks(pages)
	print(f"Made {len(chunks)} chunks")

	if args.only:
		chunks = [chunks[int(args.only)]]
		process_chunks(chunks, args.output, kg, args.limit, args.partial, args.skiperrors, True)
		dspy.inspect_history(n=1)
	else:
		process_chunks(chunks, args.output, kg, args.limit, args.partial, args.skiperrors)

	if args.aggregate:
		print("Aggregating chunks")
		aggregate_chunks(kg, args.output)
	
	if args.index:
		print("Indexing chunks")
		index = make_index(args.output)
		storage.save_index(index, f"{args.output}/index.json")
	
	if args.upload:
		print("Uploading graph")
		with GraphDatabase.driver(db_url, auth=(db_user, db_pass)) as driver:
			driver.verify_connectivity()
			aggregated_graph = storage.load_graph(f"{args.output}/aggregated.json")
			clear_database(driver)
			write_graph_to_database(aggregated_graph, driver)
	
	print("Done!")


if __name__ == "__main__":
	main()
