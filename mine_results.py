import os
import json
import storage

output_dir = "kg-gen-repo/MINE/KGs"


def read_results_json(results_dir):
	results = []
	for f in os.listdir(results_dir):
		if f.endswith("_results.json"):
			result = read_json(results_dir + "/" + f)
			results.append(result)
	return results


def result_sum(results):
	count = len(results) - 1
	score_sum = 0
	for result in results:
		if "evaluation" in result.keys():
			score_sum += result["evaluation"]
	return count, score_sum


def main():
	files = read_results_json(output_dir)
	scores_accuracy_sum = 0.0
	for file in files:
		count, score_sum = result_sum(file)
		scores_accuracy_sum += score_sum / count
		print(f"Score {score_sum} / {count} ({(score_sum/count*100):.2f}%)")
	
	# Floating point truncation probably is not an issue here
	scores_accuracy_sum /= len(files)
	print(f"Average accuracy is {scores_accuracy_sum*100:.2f}%")


if __name__ == "__main__":
	main()
