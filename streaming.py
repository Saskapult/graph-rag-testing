import time
import hashlib
from kg_gen import KGGen
from neo4j import GraphDatabase
import storage
import json
import os


# Performance optimization ideas:
# - async database uploading (it's slow with neo4j)
# - async kg-gen calls? (probably not useful using ollama)
class StreamingKGBuilder:
	def __init__(
		self,
		output_dir,
		db_url="neo4j://localhost:7687",
		db_user="neo4j",
		db_pass="no_password",
		model="openai/gpt-4o-mini",
		# The chunk buffer fills to this size before being used to create a chunk
		chunk_size=100, 
		# Chunks will overlap by this many entries 
		chunk_overlap=10,
	):
		self.output_dir = output_dir
		self.driver = GraphDatabase.driver(db_url, auth=(db_user, db_pass))
		self.kg = KGGen(model=model)

		self.chunk_size = chunk_size
		self.chunk_overlap = chunk_overlap
		self.chunk_buffer = []
		# list[(threshold, tags)]
		# self.chunk_tags = []
	
	def _process_chunk(self):
		print("Process chunk")
		# Take from chunk buffer (but leave some overlap)
		chunk_text = " ".join(self.chunk_buffer[:self.chunk_size])
		print(f"Size is {len(self.chunk_buffer[:self.chunk_size])}")
		self.chunk_buffer = self.chunk_buffer[(self.chunk_size-self.chunk_overlap):]
		print(f"Buffer is now {len(self.chunk_buffer)}")

		text_hash = hashlib.md5(chunk_text.encode()).hexdigest()
		checkpoint_filename = f"chunk-{text_hash}.json"
		checkpoint_file = f"{self.output_dir}/{checkpoint_filename}"
		chunk = None
		# TODO: collision detection
		if os.path.isfile(checkpoint_file):
			# Checkpointing might not be useful in the final implementation, but it's nice to have for testing
			print("Skip processing - load checkpoint")
			chunk = storage.load_chunk(checkpoint_file)
		else:
			assert False
			print("Generate kg")
			generate_st = time.time()
			graph = self.kg.generate(input_data=chunk_text)
			generate_en = time.time()
			generate_duration = generate_en - generate_st
			print(f"Processed in {generate_duration:.2f} seconds")

			print("Save to file")
			tags = {
				"checkpoint": checkpoint_filename
			}
			chunk = {
				"text": chunk_text,
				"hash": text_hash,
				"time": generate_duration,
				"graph": graph,
				"tags": tags,
			}
			print(f"Saving checkpoint as {tags["checkpoint"]}")
			storage.save_chunk(chunk, checkpoint_file)		

		print("Upload to database")
		tags_str = json.dumps(chunk["tags"])
		graph = chunk["graph"]

		for i, entity in enumerate(graph.entities):
			print(f"Write entity {i+1}/{len(graph.entities)}")
			self.driver.execute_query(
				"""
				MERGE (e:Entity {id: $id})
				ON CREATE SET e.tags = [$tags]
				ON MATCH SET e.tags = e.tags + $tags
				""",
				id=entity,
				tags=tags_str,
			)
		
		for i, (a, r, b) in enumerate(graph.relations):
			print(f"Write relation {i+1}/{len(graph.relations)} ({a} ~ {r} ~ {b})")
			relation = storage.to_neo4j_repr(r)
			self.driver.execute_query(
				f"""
				MATCH (a:Entity {{id: $id_a}})
				MATCH (b:Entity {{id: $id_b}})
				MERGE (a)-[r:{relation}]->(b)
				ON CREATE SET r.tags = [$tags]
				ON MATCH SET r.tags = r.tags + $tags
				""",
				id_a=a,
				id_b=b,
				tags=tags_str,
				relation=relation,
			)

	# Take in some text and maybe process some of it
	# TODO: receive input tags (document and page numbers, audio timestamps)
	def feed(self, text):
		print(f"Add {len(text.split())} words")
		self.chunk_buffer += text.split()
		# Add tags?

		while len(self.chunk_buffer) > self.chunk_size:
			print("Submit chunk")
			self._process_chunk()

	# Forces the builder to use the data in the chunk buffer regardless of the buffer's size
	def finish(self):
		print("Finish builder")
		while len(self.chunk_buffer) > 0:
			print("Submit chunk")
			self._process_chunk()
		assert len(self.chunk_buffer) == 0


def main():
	# https://www.youtube.com/watch?v=B36Ehzf2cxE
	# It doens't give us much information...
	chunks = None
	with open("inputs/Minecraft Tutorials - E01 How to Survive your First Night (UPDATED!).srt") as f:
		lines = f.readlines()
		lines = [line.strip() for i, line in enumerate(lines) if i % 4 == 2]
		chunks = lines
	# print(chunks[:10])
	# exit(0)


	# # A demo could play the audio from youtube, transcribe it, and process the text in real-time
	# chunks = [
	# 	"""
	# 	We're no strangers to love
	# 	You know the rules and so do I
	# 	A full commitment's what I'm thinkin' of
	# 	You wouldn't get this from any other guy
	# 	""",
	# 	"""
	# 	I just wanna tell you how I'm feeling
	# 	Gotta make you understand
	# 	""",
	# 	"""
	# 	Never gonna give you up, never gonna let you down
	# 	Never gonna run around and desert you
	# 	Never gonna make you cry, never gonna say goodbye
	# 	Never gonna tell a lie and hurt you
	# 	""",
	# 	"""
	# 	We've known each other for so long
	# 	Your heart's been aching, but you're too shy to say it
	# 	Inside, we both know what's been going on
	# 	We know the game and we're gonna play it
	# 	""",
	# 	"""
	# 	And if you ask me how I'm feeling
	# 	Don't tell me you're too blind to see
	# 	""",
	# 	"""
	# 	Never gonna give you up, never gonna let you down
	# 	Never gonna run around and desert you
	# 	Never gonna make you cry, never gonna say goodbye
	# 	Never gonna tell a lie and hurt you
	# 	""",
	# 	"""
	# 	Never gonna give you up, never gonna let you down
	# 	Never gonna run around and desert you
	# 	Never gonna make you cry, never gonna say goodbye
	# 	Never gonna tell a lie and hurt you
	# 	""",
	# 	"""
	# 	We've known each other for so long
	# 	Your heart's been aching, but you're too shy to say it
	# 	Inside, we both know what's been going on
	# 	We know the game and we're gonna play it
	# 	""",
	# 	"""
	# 	I just wanna tell you how I'm feeling
	# 	Gotta make you understand
	# 	""",
	# 	"""
	# 	Never gonna give you up, never gonna let you down
	# 	Never gonna run around and desert you
	# 	Never gonna make you cry, never gonna say goodbye
	# 	Never gonna tell a lie and hurt you
	# 	""",
	# 	"""
	# 	Never gonna give you up, never gonna let you down
	# 	Never gonna run around and desert you
	# 	Never gonna make you cry, never gonna say goodbye
	# 	Never gonna tell a lie and hurt you
	# 	""",
	# 	"""
	# 	Never gonna give you up, never gonna let you down
	# 	Never gonna run around and desert you
	# 	Never gonna make you cry, never gonna say goodbye
	# 	Never gonna tell a lie and hurt you
	# 	""",
	# ]
	# chunks = [c.replace("\n", "").replace("\t", "") for c in chunks]

	print("Create processor")
	# s = StreamingKGBuilder("graphs/rick_astley_1987")
	s = StreamingKGBuilder("graphs/sat_e01")
	processing_st = time.time()
	for i, c in enumerate(chunks):
		print(f"Feed chunk {i+1}/{len(chunks)}")
		s.feed(c)
	print("Finish")
	s.finish()
	processing_en = time.time()
	print(f"Done in {(processing_en - processing_st):.2f} seconds!")


if __name__ == "__main__":
	main()
