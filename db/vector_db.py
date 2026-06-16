import os
import lancedb
import pyarrow as pa
from pathlib import Path
from openai import OpenAI

DB_DIR = Path(__file__).parent.parent / "data" / "persona_db.lance"
TABLE_NAME = "persona_vault"

_client = None

def get_openai_client() -> OpenAI:
    """Instantiate and cache the OpenAI client."""
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set in .env.")
        _client = OpenAI(api_key=api_key)
    return _client

def get_embedding(text: str) -> list[float]:
    """Generates a 1536-dimensional embedding using OpenAI text-embedding-3-small."""
    client = get_openai_client()
    text = text.replace("\n", " ").strip()
    if not text:
        return [0.0] * 1536
        
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def get_vector_db():
    """Connects to the local serverless LanceDB instance."""
    DB_DIR.parent.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(DB_DIR))

def init_vector_table() -> lancedb.table.Table:
    """Creates or overwrites the persona_vault table with the proper PyArrow schema."""
    db = get_vector_db()
    
    # Exposing explicit schema to prevent mismatch during pyarrow inference
    schema = pa.schema([
        pa.field("vector", pa.list_(pa.float32(), 1536)),
        pa.field("text", pa.string()),
        pa.field("source", pa.string()),
        pa.field("category", pa.string())
    ])
    
    # Overwrite if exists
    if TABLE_NAME in db.list_tables().tables:
        db.drop_table(TABLE_NAME)
        
    table = db.create_table(TABLE_NAME, schema=schema)
    return table

def add_persona_chunks(chunks: list[dict]) -> None:
    """
    Inserts a list of document chunks into the LanceDB table.
    Each chunk dict should contain: 'text', 'source', 'category'.
    Embeddings are generated automatically.
    """
    if not chunks:
        return
        
    table_data = []
    for chunk in chunks:
        text = chunk["text"]
        if not text.strip():
            continue
        vector = get_embedding(text)
        table_data.append({
            "vector": vector,
            "text": text,
            "source": chunk["source"],
            "category": chunk["category"]
        })
        
    db = get_vector_db()
    if TABLE_NAME not in db.list_tables().tables:
        table = init_vector_table()
    else:
        table = db.open_table(TABLE_NAME)
        
    table.add(table_data)

def search_persona(query: str, limit: int = 5) -> list[dict]:
    """
    Performs a semantic vector search against the Persona vault.
    Returns list of dicts: [{'text': str, 'source': str, 'category': str, '_distance': float}]
    """
    db = get_vector_db()
    if TABLE_NAME not in db.list_tables().tables:
        return []
        
    query_vector = get_embedding(query)
    table = db.open_table(TABLE_NAME)
    
    # Execute search
    results = table.search(query_vector).limit(limit).to_list()
    
    # Format results
    search_results = []
    for r in results:
        search_results.append({
            "text": r["text"],
            "source": r["source"],
            "category": r["category"],
            "distance": r.get("_distance", 0.0)
        })
    return search_results
