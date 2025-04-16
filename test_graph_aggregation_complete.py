import storage
import argparse
import os


def missing_relationships(sub, big):
	missing = []
	for r in sub.relations:
		if not r in big.relations:
			missing.append(r)
	return missing


def main():
	"""
	This tests that all of the relationships in each chunk graph are presnt in
	the aggregated graph. 
	If they are, then we can eliminate the hacky index I've made and integrate 
	sourcing directly into the graph database. 
	"""

	parser = argparse.ArgumentParser()
	parser.add_argument("dir")
	args = parser.parse_args()

	print("Loading graphs...")
	aggregated = storage.load_graph(f"{args.dir}/aggregated.json")
	others = [storage.load_chunk(f"{args.dir}/{f}")["graph"] for f in os.listdir(args.dir) if f.startswith("chunk-")]

	heretical = False
	for i, other in enumerate(others):
		print(f"Test chunk {i+1}... ", end="")
		missing = missing_relationships(other, aggregated)
		if missing:
			print("HERETICAL!")
			heretical = True
			for a, r, b in missing:
				print(f"Missing: {a} -{{{r}}}-> {b}")
		else:
			print("Okay!")
	
	if heretical:
		print("Looks bad!")
	else:
		print("Looks good!")


if __name__ == "__main__":
	main()
