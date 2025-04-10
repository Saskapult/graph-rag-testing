import os
import json
import storage

output_dir = "kg-gen-repo/MINE/KGs"
sus_threshold = 0.1


def read_results_json(results_dir):
	filenames = []
	contents = []
	for f in os.listdir(results_dir):
		if f.endswith("_results.json"):
			filenames.append(f)
			content = read_json(results_dir + "/" + f)
			contents.append(content)
	return filenames, results


def result_sum(results):
	count = len(results) - 1
	score_sum = 0
	for result in results:
		if "evaluation" in result.keys():
			score_sum += result["evaluation"]
	return count, score_sum


def main():
	names, files = read_results_json(output_dir)

	suspicious = []
	scores_accuracy_sum = 0.0
	for name, file in zip(names, files):
		count, score_sum = result_sum(file)
		accuracy = score_sum / count
		scores_accuracy_sum += accuracy
		print(f"{name} score {score_sum} / {count} ({(score_sum/count*100):.2f}%)")
		if accuracy <= sus_threshold:
			print("\tThat's suspicious")
			suspicious.append((name, accuracy))

	# Floating point truncation probably is not an issue here
	scores_accuracy_sum /= len(files)
	print(f"Average accuracy is {scores_accuracy_sum*100:.2f}%")

	if len(suspicious) > 0:
		print(f"Found {len(suspicious)} results with accuracy less than {sus_threshold*100:.2f}%:")
		for name, accuracy in suspicious:
			print(f"'{name}' - {accuracy*100:.2f}%")


if __name__ == "__main__":
	main()
