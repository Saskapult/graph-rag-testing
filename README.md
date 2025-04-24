# Graph RAG Testing

This might need to be cloned with `git clone --recursive` so that you get the submodules
If you don't do this you won't have the right packages. 

## Usage
(assuming you're not on Cedar)

- Set your `OPENAI_API_KEY` variable
- Set your `OPENAI_API_KEY` variable to the model you wish to use for processing 
- `cd neo4j && docker compose up -d && cd ..`
- `uv run process.py --only 4 -au -o graphs/<output name> inputs/<your input pdf>`
	- `--only 4` to only process the first four chunks (reduces testing costs)
	- `-a` to aggregate the chunks
	- `-u` to upload the aggregated graph to the graph database
- `uv run query.py graphs/<same output name> "How is FEMA related to NIMS?"`

### Environment
| Name | Function |
| - | - | 
| `DB_HOST` | graph database host url |
| `DB_USER` | graph database user | 
| `DB_PASSWORD` | graph database password | 
| `DB_DATABASE` | graph database database name | 
| `PROCESSING_MODEL` | model used for processing |
| `QUERY_MODEL` | model used for queries |


## What is this doing?
I'll describe my longest workflow, but most of these stages can be executed independently. 

- Build an apptainer with ollama/phi-4
- Queue a job on Cedar
	- Start the apptainer
	- Execute the processing script in that apptainer
		- Read a document, split it into chunks
		- Create a knowledge graph from each chunk
			- This is checkpointed to avoid repeated work
			- Write each knowledge graph to disk
		- Aggregate the knowledge graphs, save the result to disk
	- Stop the apptainer 
- Download the output from Cedar
- Upload the aggregated knowledge graph to a graph database
- Answer a query
	- Create a knowledge graph from that query
	- Find graph database nodes corresponding to nodes in the query's graph
	- Collect related nodes and relations (based on [DALK](https://arxiv.org/pdf/2405.04819))
	- Filter those by relevance (see above)
	- Use the filtered information to generate a response 
	- Trace the filtered information back to its source chunks in the original document
