from kg_gen import KGGen
import storage
import os s

model = "ollama/phi4"
essays_file = "kg-gen-repo/MINE/essays.json"
output_dir = "kg-gen-repo/MINE/KGs"


def main():
	os.makedirs(output_dir, exist_ok=True)

	kg = KGGen(
		model=model,
	)
	
	essays = storage.load_json(essays_file)
	for i, essay in enumerate(essays):
		print(f"Process essay {i+1}/{len(essays)}")

		output_file = f"{output_dir}/{i+1}_result.json"
		if os.path.isfile(output_file):
			print("\texists, skip")
			continue

		graph = kg.generate(
			input_data=essay["content"],
			context=essay["topic"],
		)
		storage.save_graph(graph, output_file)
	
	print("Done!")


if __name__ == "__main__":
	main()
