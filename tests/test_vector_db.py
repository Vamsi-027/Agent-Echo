import pytest
import os
import shutil
from pathlib import Path
from unittest.mock import patch

from db.vector_db import (
    init_vector_table,
    add_persona_chunks,
    search_persona,
    get_vector_db,
    TABLE_NAME
)

# Test LanceDB database directory
TEST_LANCE_DIR = Path(__file__).parent / "test_persona_db.lance"

@pytest.fixture
def mock_db_env():
    # Set the DB path to a test location
    with patch("db.vector_db.DB_DIR", TEST_LANCE_DIR):
        # Clean up test database directory
        if TEST_LANCE_DIR.exists():
            shutil.rmtree(TEST_LANCE_DIR)
            
        yield TEST_LANCE_DIR
        
        # Clean up test database directory after test
        if TEST_LANCE_DIR.exists():
            shutil.rmtree(TEST_LANCE_DIR)

@pytest.fixture
def mock_embedding():
    # Create a mock embedding vector (1536 elements)
    mock_vector = [0.1] * 1536
    with patch("db.vector_db.get_embedding", return_value=mock_vector):
        yield mock_vector

def test_init_vector_table(mock_db_env):
    """Test table creation and schema fields."""
    table = init_vector_table()
    assert table is not None
    
    db = get_vector_db()
    assert TABLE_NAME in db.list_tables().tables

def test_add_and_search_chunks(mock_db_env, mock_embedding):
    """Test adding chunks to LanceDB and searching them semantically."""
    init_vector_table()
    
    chunks = [
        {"text": "Python and AI development is my specialty.", "source": "resume.txt", "category": "experience"},
        {"text": "Avoid using corporate buzzwords on social media.", "source": "style.txt", "category": "style"}
    ]
    
    add_persona_chunks(chunks)
    
    # Verify search returns matches
    # Since get_embedding is mocked to return the same vector, search_persona will find these records
    results = search_persona("Python programming advice", limit=5)
    assert len(results) == 2
    
    # Check details of the result
    texts = [r["text"] for r in results]
    assert "Python and AI development is my specialty." in texts
    assert "Avoid using corporate buzzwords on social media." in texts
    
    # Verify fields are correctly populated
    for r in results:
        assert "source" in r
        assert "category" in r
        assert "distance" in r
