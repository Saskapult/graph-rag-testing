import os
import age 

db_url = os.getenv("DB_HOST", "localhost:5432")
db_user = os.getenv("DB_USER", "postgres")
db_pass = os.getenv("DB_PASSWORD", "no_password")
db_base = os.getenv("DB_DATABASE", "db")


def setup(ag):
	ag.execCypher("MATCH (n) DETACH DELETE n")
	ag.execCypher("""
	CREATE 
		(portia:Person {name: "Portia"}), 
		(bianca:Person {name: "Bianca"}),
		(fabian:Person {name: "Fabian"})
	CREATE 
		(bianca)-[:EDGE]->(portia),
		(portia)-[:EDGE]->(fabian)
	""")
	ag.commit()


def test_comprehensions(ag):
	cursor = ag.execCypher("""
	MATCH p = (a:Person)
	RETURN [n in nodes(p) | n.name] as nodes
	""")
	for row in cursor:
		print(row)


def test_shortest(ag):
	cursor = ag.execCypher("""
	MATCH p = SHORTEST 1 (a:Person {name: "Bianca"})-[r]-+(b:Person {name: "Fabian"})
	RETURN nodes(p) as nodes
	""")
	for row in cursor:
		print(row)


def main():
	ag = age.connect(
		dbname=db_base,
		user=db_user,
		password=db_pass,
		host="".join(db_url.split(":")[:-1]),
		port=db_url.split(":")[-1],
		graph="my_graph",
	)

	print("Setting up...")
	setup(ag)

	print("Running test...")
	# test_comprehensions(ag)
	test_shortest(ag)


if __name__ == "__main__":
	main()
