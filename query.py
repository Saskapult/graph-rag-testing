from neo4j import GraphDatabase
from kg_gen import KGGen, Graph
import json 
import os
from litellm import completion
import argparse
import storage

db_url = os.getenv("DB_HOST", "neo4j://localhost:7687")
db_user = os.getenv("DB_USER", "neo4j")
db_pass = os.getenv("DB_PASSWORD", "no_password")
db_base = os.getenv("DB_DATABASE", "neo4j")

query_model = os.getenv("QUERY_MODEL", "openai/gpt-4o-mini")


def path_based_subgraph(eg, driver):
	gpathq = []
	segment = []
	e1 = eg[0]
	candidates = eg[1:]
	while len(candidates) != 0:
		print(f"e1: '{e1}'")
		print(f"candidates: {candidates}")

		neighbours, summary, _ = driver.execute_query("""
			MATCH p = ALL SHORTEST (e1:Entity {id: $e1})-[r]-{1,2}(neighbours:Entity)
			RETURN neighbours.id AS id, [e in r | TYPE(e)] AS edges, [n in nodes(p) | n.id] AS nodes
			ORDER BY length(p)
			""",
			e1=e1,
			database_=db_base,
		)
		for e2, edges, nodes in neighbours:
			# if e2 != e1:
			# 	print(e2, edges, nodes)
			if e2 != e1 and e2 in candidates:
				print(f"path to '{e2}'")

				# Interleave lists
				for n, e in zip(nodes, edges):
					segment.append(n)
					segment.append(e.replace("_", " "))
				segment.append(nodes[len(nodes)-1])

				print(" -> ".join(segment))

				e1 = e2
				candidates.remove(e2)
				break

		# Not found in k hops
		if len(candidates) != 0:
			print("New segment")
			gpathq.append(segment)
			e1 = candidates[0]
			candidates = candidates[1:]
	gpathq.append(segment)

	print("Path-based sub-graph:")
	for path in gpathq:
		print(" -> ".join(path))
	
	return gpathq


def neighbour_based_subgraph(query, eg, driver):
	gneiq = []
	for e in eg:
		print(f"neighbours of {e}")
		e_neighbours, summary, _ = driver.execute_query("""
			MATCH (e:Entity {id: $e})-[r]->{1}(neighbours:Entity)
			RETURN DISTINCT neighbours.id AS id, [e in r | TYPE(e)] AS edge
			""",
			e=e,
			database_=db_base,
		)
		print(e_neighbours)

		for ep, rel in e_neighbours:
			# The relationship is returned as a list, but it only has one element
			gneiq.append([e, rel[0].replace("_", " "), ep])
			# How semantic relevance? 
			# It seem to be based on the application, see MindMap_revised.py line 638
			# if is_relevant(ep):
			# 	ep_neighbours = """
			# 	MATCH (ep:Entity {id: ep})--{1}(neighbours:Entity)
			# 	RETURN DISTINCT neighbours.id AS id
			# 	"""
			# 	for e_nei in ep_neighbours:
			# 		gneiq.append((e_nei, "", ep))
	
	print("Neighbour-based sub-graph:")
	for path in gneiq:
		print(" -> ".join(path))
	
	return gneiq


def path_evidence(q, gpathq, k, completion_fn, index):
	gq_str = "\n".join(["->".join(v) for v in gpathq])
	# Table 15
	pself = f"""
		There is a question and some knowledge graph. The knowledge graphs follow entity->relationship->entity list format.
		Graph: 
		{gq_str}

		Question:
		{q}

		Please rerank the knowledge graph and output at most {k} important and relevant triples for solving the given question. Output the reranked knowledge in the following format:
		{"\n".join([f"Reranked Triple{i+1}: xxx -->xxx" for i in range(0, k)])}

		Answer:
	""".replace("\t", "")

	# print("pself:")
	# print(pself)
	# print()

	# Extract relationship triples
	gselfq = []
	for line in completion_fn(pself).choices[0].message.content.split("\n"):
		line = line[len("Reranked TripleN:"):]
		a, r, b = [v.strip() for v in line.split("-->")]
		gselfq.append((a, r, b))

	# Try to match sources 
	# Could return this, the raw relations, and the plain language relations
	sources = []
	for triple in gselfq:
		print(f"Trying to source {triple}")
		line = line[len("Reranked TripleN:"):]
		if triple in index:
			s = index[triple]
			print(f"Relation {triple} comes from chunk(s) {[c for c, _, _ in s]}")
			sources.append(s)
		else:
			print(f"WARN: Unrecongized relation {triple}")
			sources.append([])

	# Table 16
	pinference = f"""
		There are some knowledge graph paths. They follow entity->relationship->entity format.

		{"\n".join([f"Reranked Triple{i+1}: {a} --> {r} --> {b}" for i, (a, r, b) in enumerate(gselfq)])}

		Use the knowledge graph information. Try to convert them to natural language, respectively.
		Use single quotation marks for entity name and relation name.
		And name them as Path-based Evidence 1, Path-based Evidence 2,...

		Output:
	""".replace("\t", "")

	# print("pinference:")
	# print(pinference)
	# print()

	# This is gathered to be the output because it is used in table 17
	# Statement extraction
	a = []
	# It splits these with a double newline 
	for line in completion_fn(pinference).choices[0].message.content.split("\n\n"):
		a.append(line[len("Path-based Evidence 1: "):].strip())

	# print("a:")
	# print(a)
	# print()

	return a, sources


def dalk_query(query, kg, driver, completion_fn, index):
	q = query
	print(f"query: '{q}'")
	qg = kg.generate(
		input_data=q,
	)
	e = list(qg.entities)
	print(f"entities: {e}")

	# Compute he
	# he = [st_model.encode(entity) for entity in e]
	# Find links with similarity to hg
	# Find of like this but you extract the one with the highest similarity
	# eg = st_model.similairties(he, hg)
	# We don't actually need to do that I think
	eg = e 

	gpathq = path_based_subgraph(eg, driver)
	gneiq = neighbour_based_subgraph(query, eg, driver)
	
	# Both again, see what happens
	path_statements, path_sources = path_evidence(query, gpathq + gneiq, 5, completion_fn, index)
	# Not described in the paper?
	# MindMap_revised.py uses different prompts than the paper too 
	neighbourstuff = None 

	panswer = f"""
		Question: {q}

		You have some knowledge information in the following:
		###{"\n".join([f"Path-based Evidence {i+1}: {s}" for i, s in enumerate(path_statements)])}
		###{neighbourstuff}

		Answer: Let's think step by step:
	""".replace("\t", "")

	# print("panswer:")
	# print(panswer)
	# print()

	answer = completion_fn(panswer).choices[0].message.content

	# print("answer:")
	# print(answer)
	# print()	

	return {
		"query": query,
		"answer": answer,
		"statements": path_statements,
		"sources": path_sources,
	}


def show_answer(answer_dict):
	print("answer:")
	print(answer_dict["answer"])
	print("sources:")
	for i, (statement, sources) in enumerate(zip(answer_dict["statements"], answer_dict["sources"])):
		print(f"{i+1}. {statement}")
		if len(sources) > 0:
			pagesrcs = []
			chunks = []
			for c, st, en in sources:
				chunks.append(c)
				for p in range(st, en+1):
					pagesrcs.append(str(p))
			print(f"  - pages {", ".join(set(pagesrcs))} (chunks {", ".join(chunks)})")
		else:
			print(f"  - no source provided!")


# Demonstrates pulling source chunks for a set of statements
# Retuns a list of source texts becuase one statment can draw from multiple chunks
def pull_source_text(path, sources):
	texts = []
	for c, st, en in sources:
		chunk = storage.load_chunk(f"{path}/chunk-{c}-{st}-{en}.json")
		texts.append(chunk["source_text"])
	return texts


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("files")
	parser.add_argument("query")
	args = parser.parse_args()

	print("Read index")
	index = storage.load_index(f"{args.files}/index.json")
	print(index)

	kg = KGGen(
		model=query_model,
	)

	completion_fn = lambda q: completion(
		model=query_model,
		messages=[{"content": q, "role": "user"}]
	)

	with GraphDatabase.driver(db_url, auth=(db_user, db_pass)) as driver:
		driver.verify_connectivity()

		a = dalk_query(args.query, kg, driver, completion_fn, index)
		show_answer(a)

		# For demo 
		source_chunk_texts = [pull_source_text(args.files, s) for s in a["sources"]]
		print(source_chunk_texts)


if __name__ == "__main__":
	main()
