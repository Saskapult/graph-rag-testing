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
	for f in os.listdir(args.files):
		m = re.match(r"chunk-(\d+)-\d+-\d+.json", f)
		if m:
			j = storage.load_json(f"{args.files}/{f}")
			if "time" in j.keys():
				chunk = m.group(1)
				chunks.append(int(chunk))
				time = j["time"]
				times.append(time)
	
	mean = sum(times) / len(times)
	median = sorted(times)[len(times)//2]
	print(f"Mean time {mean:.2f}s")
	print(f"Median time {median:.2f}s")

	plt.subplot(2, 1, 1)
	plt.title("Time to process chunk")
	plt.xlabel("chunk")
	plt.ylabel("time (s)")
	plt.scatter(chunks, times)
	
	plt.subplot(2, 1, 2)
	plt.title("Time distrobution")
	plt.hist(times)

	plt.show()


if __name__ == "__main__":
	main()
