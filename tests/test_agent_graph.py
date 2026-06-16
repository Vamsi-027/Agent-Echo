import pytest
import sqlite3
import os
from pathlib import Path
from generator.agent_graph import (
    compiled_graph,
    route_after_digest,
    route_after_pillar,
    route_after_format,
    aggregate_digest_node,
    classify_pillar_node,
    select_format_node,
    retrieve_persona_context_node
)
from db.db import init_db
from langgraph.graph import END

TEST_DB_PATH = Path(__file__).parent / "test_agent_graph.db"

@pytest.fixture
def test_db():
    # Set environment variable to redirect DB paths
    os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)
    
    # Clean up sidecars
    for suffix in ["", "-wal", "-shm"]:
        p = TEST_DB_PATH.with_name(TEST_DB_PATH.name + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
                
    init_db(db_path=TEST_DB_PATH)
    
    yield TEST_DB_PATH
    
    # Teardown
    if "DATABASE_PATH" in os.environ:
        del os.environ["DATABASE_PATH"]
        
    for suffix in ["", "-wal", "-shm"]:
        p = TEST_DB_PATH.with_name(TEST_DB_PATH.name + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

def test_graph_compilation():
    """Verify that the compiled LangGraph object compiles without throwing errors."""
    assert compiled_graph is not None
    # Validate node names present in graph
    assert "aggregate_digest" in compiled_graph.nodes
    assert "classify_pillar" in compiled_graph.nodes
    assert "select_format" in compiled_graph.nodes
    assert "retrieve_persona_context" in compiled_graph.nodes
    assert "generate_drafts" in compiled_graph.nodes

def test_conditional_routing_after_digest():
    """Verify routing decisions after the daily digest node."""
    # 1. Success case (should route to classify_pillar)
    state_success = {
        "date": "2026-06-14",
        "digest": {"suggested_pillar": "lesson_learned"},
        "status": "success",
        "pillar": None,
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "error": None
    }
    assert route_after_digest(state_success) == "classify_pillar"
    
    # 2. No activity case (should route to END)
    state_no_act = {
        "date": "2026-06-14",
        "digest": None,
        "status": "no_activity",
        "pillar": None,
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "error": None
    }
    assert route_after_digest(state_no_act) == END
    
    # 3. Digest suggested pillar is 'none' (should route to END)
    state_none_pillar = {
        "date": "2026-06-14",
        "digest": {"suggested_pillar": "none"},
        "status": "success",
        "pillar": None,
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "error": None
    }
    assert route_after_digest(state_none_pillar) == END

def test_conditional_routing_after_pillar():
    """Verify routing decisions after the pillar classifier node."""
    # 1. Valid pillar (should route to select_format)
    state_valid_pillar = {
        "date": "2026-06-14",
        "digest": {},
        "status": "success",
        "pillar": "technical_insight",
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "error": None
    }
    assert route_after_pillar(state_valid_pillar) == "select_format"
    
    # 2. None pillar (should route to END)
    state_none_pillar = {
        "date": "2026-06-14",
        "digest": {},
        "status": "success",
        "pillar": "none",
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "error": None
    }
    assert route_after_pillar(state_none_pillar) == END

def test_conditional_routing_after_format():
    """Verify routing decisions after the format selection node."""
    # 1. Success case (should route to retrieve_persona_context)
    state_success = {
        "date": "2026-06-14",
        "digest": {},
        "status": "success",
        "pillar": "lesson_learned",
        "secondary_pillar": None,
        "format_type": "text",
        "persona_context": None,
        "drafts": [],
        "error": None
    }
    assert route_after_format(state_success) == "retrieve_persona_context"
    
    # 2. Failure case (should route to END)
    state_fail = {
        "date": "2026-06-14",
        "digest": {},
        "status": "failed",
        "pillar": "lesson_learned",
        "secondary_pillar": None,
        "format_type": "text",
        "persona_context": None,
        "drafts": [],
        "error": "Format selection failed"
    }
    assert route_after_format(state_fail) == END

def test_retrieve_persona_context_node_empty():
    """Verify retrieve_persona_context_node behaves correctly when highlights are missing or empty."""
    state = {
        "date": "2026-06-14",
        "digest": None,
        "status": "success",
        "pillar": "lesson_learned",
        "secondary_pillar": None,
        "format_type": "text",
        "persona_context": None,
        "drafts": [],
        "error": None
    }
    res = retrieve_persona_context_node(state)
    assert res == {"persona_context": ""}
