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


# Returns dict[int, ..dict[int, int]]
# Stops clustering once there are only cutoff nodes to cluster 
def recursive_louvain(cutoff=10):
	results, _, _ = driver.execute_query("""
		MATCH (source:Entity)
		OPTIONAL MATCH (source)-[r]->(target:Entity)
		RETURN gds.graph.project(
			'louvain_communities',
			source,
			target,
			{}
		)
	""")


# Recursion step 
def _louvain_recurse(graph_name, cutoff):
	results, _, _ = driver.execute_query("""
		CALL gds.louvain.stream('louvain_communities')
		YIELD nodeId, communityId
		RETURN communityId as communities, COUNT(DISTINCY nodeId) as members
		ORDER BY members DESC
		LIMIT 10
	""")
	communities = list(results.co)
	if members < cutoff:
		return 42
	else:
		results, _, _ = driver.execute_query("""
			MATCH (source:Entity)
			OPTIONAL MATCH (source)-[r]->(target:Entity)
			RETURN gds.graph.project(
				'louvain_communities',
				source,
				target,
				{}
			)
		""")
		return _louvain_recurse()


def group_summary(entities):
	class SummarySignature(dspy.Signature):
		"""
		Given a collection of entities, find one or two words to describe them.
		"""
		entities: list[str] = dspy.InputField()
		description: str = dspy.OutputField()	
	g = dspy.Predict(SummarySignature)
	answer = g(entities=entities)
	# print(answer)
	return answer.description


def main():
	lm = dspy.LM(query_model)
	dspy.configure(lm=lm)

	k = 10

	with GraphDatabase.driver(db_url, auth=(db_user, db_pass)) as driver:
		driver.verify_connectivity()

		# Generate louvain 
		# For each group, label it 

		# or 

		# Generate louvain 
		# Recurse down 
		# Summarize
		# Recurse up 

		# Find all communities and their counts 
		records, _, _ = driver.execute_query("""
			MATCH (n:Entity) 
			RETURN DISTINCT n.louv_community as community, COUNT(DISTINCT n.id) as members
			ORDER BY members DESC
		""")
		print(f"Found {len(records)} communities")

		# Select communities with sufficient count (otherwise we'll have thousands)
		records = [record for record in records if record["members"] >= 10]
		print(f"Found {len(records)} with at least {k} members")

		for community, count in records:
			result, _, _ = driver.execute_query("""
				MATCH (n:Entity { louv_community: $cid }) 
				RETURN n.id as id
			""", cid=community)
			print(f"Community {community} has {count} members")

			nodes = [r["id"] for r in result]
			summary = group_summary(nodes)
			print(f" -- label is '{summary}'")

			input("Continue...")
		print("Done!")


if __name__ == "__main__":
	main()
