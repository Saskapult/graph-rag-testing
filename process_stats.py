import storage
import regex as re 
import os
import argparse 
import matplotlib.pyplot as plt


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("files")
	args = parser.parse_args()

	chunks = []
	times = []
	for f in os.listdir(graphs_path):
		m = re.match(r"chunk-(\d+)-\d+-\d+.json")
		if m:
			j = storage.load_json(f"{graphs_path}/{f}")
			if "time" in j.keys():
				chunk = m.group(1)
				chunks.append(int(chunk))
				time = j["time"]
				times.appedn(time)
	
	plt.scatter(chunks, times)
	plt.hist(times)
	plt.show()


if __name__ == "__main__":
	main()
