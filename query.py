from neo4j import GraphDatabase
from kg_gen import KGGen, Graph
import json 
import os
import argparse
import storage
import regex as re
import dspy
import age

db_url = os.getenv("DB_HOST", "neo4j://localhost:7687")
db_user = os.getenv("DB_USER", "neo4j")
db_pass = os.getenv("DB_PASSWORD", "no_password")
db_base = os.getenv("DB_DATABASE", "neo4j")

query_model = os.getenv("QUERY_MODEL", "openai/gpt-4o-mini")


def k_hops_neighbours_postgres(e, ag, k=2):
	cursor = ag.execCypher("""
		MATCH p=(a:Entity {id: %s})-[r*..%s]->(b:Entity) 
		RETURN b.id as idk, nodes(p) as idk2, r as idk3
	""", params=(e, k), cols=["name", "nodes", "edges"])

	result = []
	for name, nodes, edges in cursor:
		result.append((
			storage.from_neo4j_repr(name),
			[storage.from_neo4j_repr(node.properties["id"]) for node in nodes],
			[storage.from_neo4j_repr(edge.label) for edge in edges],
			[[int(i) for i in s.split(",")] for edge in edges],
		))
	
	# Sort by closest first 
	result.sort(key=lambda v: len(v[2]))

	return result


def k_hops_neighbours_neo4j(e1, driver, k=2):
	neighbours, _, _ = driver.execute_query("""
		MATCH p = ALL SHORTEST (e1:Entity {id: $e1})-[r*..K_VALUE]-(neighbours:Entity)
		RETURN neighbours.id AS id, [n in nodes(p) | n.id] AS nodes, [e in r | TYPE(e)] AS edges, [e in r | e.sources] AS sources
		ORDER BY length(p)
		""".replace("K_VALUE", str(k)),
		e1=e1,
		database_=db_base,
	)

	result = []
	for node, nodes, edges, sources in neighbours:
		result.append((
			storage.from_neo4j_repr(node),
			[storage.from_neo4j_repr(n) for n in nodes],
			[storage.from_neo4j_repr(e) for e in edges],
			[[int(i) for i in s.split(",")] for s in sources],
		))

	return result


# Returns [(node, nodes to get there, edges to get there, sources for those edges)]
def k_hops_neighbours(e, graph, k=2):
	if isinstance(graph, age.age.Age):
		return k_hops_neighbours_postgres(e, graph, k)
	else:
		return k_hops_neighbours_neo4j(e, graph, k)


def path_based_subgraph(eg, driver):
	gpathq = []
	segment = []
	e1 = eg[0]
	candidates = eg[1:]
	while len(candidates) != 0:
		print(f"e1: '{e1}'")
		print(f"candidates: {candidates}")

		neighbours = k_hops_neighbours(e1, driver, 2)
		for e2, edges, nodes, sources in neighbours:
			# if e2 != e1:
			# 	print(e2, edges, nodes)
			if e2 != e1 and e2 in candidates:
				print(f"path to '{e2}'")

				# Interleave lists
				for n, e in zip(nodes, edges):
					segment.append(n)
					segment.append(e)
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

		e_neighbours = k_hops_neighbours(e, driver, k=1)
		# print(e_neighbours)

		for ep, _, rel, sources in e_neighbours:
			# The relationship is returned as a list, but it only has one element
			print(e, ep, rel)
			gneiq.append((e, rel[0], ep))
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


def path_evidence(q, gpathq, k, index):
	class PSelfSignature(dspy.Signature):
		"""
		There is a question and some knowledge graph triples. Rerank the knowledge graph triples and output at most k important and relevant triples for solving the given question.
		"""
		question: str = dspy.InputField()
		k: int = dspy.InputField(desc="the numer of tiples to output")
		knowledge_graph: list[tuple[str, str, str]] = dspy.InputField()
		reranked_knowledge_graph: list[tuple[str, str, str]] = dspy.OutputField(desc="reranked knowledge graph")
	
	pself = dspy.Predict(PSelfSignature)
	gselfq = pself(question=q, knowledge_graph=gpathq, k=k).reranked_knowledge_graph

	# Try to match sources 
	# Could return this, the raw relations, and the plain language relations
	sources = []
	for triple in gselfq:
		print(f"Trying to source {triple}")
		if triple in index:
			s = index[triple]
			print(f"Relation {triple} comes from chunk(s) {[c for c, _, _ in s]}")
			sources.append(s)
		else:
			print(f"WARN: Unrecongized relation {triple}")
			sources.append([])

	class PInferenceSignature(dspy.Signature):
		"""
		There are some knowledge graph paths. Try to convert them to natural language, respectively.
		"""
		knowledge_graph_paths: list[tuple[str, str, str]] = dspy.InputField()
		natural_language_paths: list[tuple[str, str, str]] = dspy.OutputField()
	
	pinference = dspy.Predict(PInferenceSignature)
	a = pinference(knowledge_graph_paths=gselfq).natural_language_paths

	return a, sources


def dalk_query(query, kg, driver, index, k):
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
	print("gpathq", gpathq)
	gneiq = neighbour_based_subgraph(query, eg, driver)
	print("gneiq", gpathq)
	
	# Both again, see what happens
	path_statements, path_sources = path_evidence(query, gpathq + gneiq, k, index)
	# Not described in the paper?
	# MindMap_revised.py uses different prompts than the paper too 
	neighbourstuff = None 

	class PAnswerSignature(dspy.Signature):
		"""
		Answer the question using the knowledge graph information. 
		"""
		question: str = dspy.InputField()
		path_based_evidence: list[tuple[str, str, str]] = dspy.InputField()
		neighbour_based_evidence: list[tuple[str, str, str]] = dspy.InputField()
		answer: str = dspy.OutputField()
	
	panswer = dspy.Predict(PAnswerSignature)
	answer = panswer(question=q, path_based_evidence=path_statements, neighbour_based_evidence=[]).answer

	return {
		"query": query,
		"answer": answer,
		"statements": path_statements,
		"sources": path_sources,
	}


def show_answer(answer_dict):
	print("answer:")
	print(answer_dict["answer"])
	print()
	print("sources:")
	for i, (statement, sources) in enumerate(zip(answer_dict["statements"], answer_dict["sources"])):
		print(f"{i+1}. {statement}")
		if len(sources) > 0:
			pagesrcs = []
			chunks = []
			for c, st, en in sources:
				chunks.append(str(c))
				for p in range(st, en+1):
					pagesrcs.append(str(p))
			pagesrcs = list(set(pagesrcs))
			pagesrcs.sort()
			print(f"  - pages {", ".join(pagesrcs)} (chunk{"s" if len(chunks) > 1 else ""} {", ".join(chunks)})")
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
	parser.add_argument('-k', nargs='?', const=5, type=int)
	parser.add_argument("--postgres", action="store_true")
	args = parser.parse_args()

	print("Read index")
	index = storage.load_index(f"{args.files}/index.json")

	lm = dspy.LM(query_model)

	kg = KGGen(
		model=query_model,
	)

	if args.postgres:
		driver = age.connect(
			dbname=db_base,
			user=db_user,
			password=db_pass,
			host="".join(db_url.split(":")[:-1]),
			port=db_url.split(":")[-1],
			graph="my_graph",
		)
		a = dalk_query(args.query, kg, driver, index, args.k)
		print()
		show_answer(a)

		# For demo 
		source_chunk_texts = [pull_source_text(args.files, s) for s in a["sources"]]
		print()
		print("source chunks:")
		for i, chunks in enumerate(source_chunk_texts):
			print(f"{i+1}. '{"' and '".join(chunks)}'")
	else:
		with GraphDatabase.driver(db_url, auth=(db_user, db_pass)) as driver:
			driver.verify_connectivity()

			a = dalk_query(args.query, kg, driver, index, args.k)
			print()
			show_answer(a)

			# For demo 
			source_chunk_texts = [pull_source_text(args.files, s) for s in a["sources"]]
			print()
			print("source chunks:")
			for i, chunks in enumerate(source_chunk_texts):
				print(f"{i+1}. '{"' and '".join(chunks)}'")


if __name__ == "__main__":
	main()
