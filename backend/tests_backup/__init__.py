import os

# tests never call a model unless they patch one in; set STRUCTURE_LLM=auto explicitly to test tier 2 through ingest
os.environ.setdefault("STRUCTURE_LLM", "off")
