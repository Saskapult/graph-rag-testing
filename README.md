# Graph RAG Testing

This might need to be cloned with `git clone --recursive` so that you get the kg-gen fork.
If you don't do this you won't have kg-gen and also the default kg-gen throws errors sometimes. 

## Usage
- Set your `OPENAI_API_KEY` variable
- `cd neo4j && docker compose up -d && cd ..`
- `uv run process.py --only 4 -iau -o graphs/<output name> inputs/<your input pdf>`
	- `--only 4` to only process the first four chunks (reduces testing costs)
	- `-i` to index the chunks
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
