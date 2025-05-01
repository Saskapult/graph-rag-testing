import query
import os
from kg_gen import KGGen
from neo4j import GraphDatabase

db_url = os.getenv("DB_HOST", "neo4j://localhost:7687")
db_user = os.getenv("DB_USER", "neo4j")
db_pass = os.getenv("DB_PASSWORD", "no_password")
driver = GraphDatabase.driver(db_url, auth=(db_user, db_pass))
kg = KGGen(model=os.getenv("QUERY_MODEL", "openai/gpt-4o-mini"))
n = 5
question = "Where does FEMA get its funding?"


def main():
	responses = [query.query_hack(question, kg, driver, k=5) for _ in range(0, 5)]
	
	equal = True
	for response in responses[1:]:
		if response != responses[0]:
			equal = False
			break
	
	if equal:
		print(f"It's deterministic (n={n})")
	else:
		print(f"It's nondeterministic (n={n})")


if __name__ == "__main__":
	main()

