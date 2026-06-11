"""Tests for User Story 7: Performance validation (SC-001, SC-002)."""

import time
import pytest
import hashlib

from canonical.factory import CanonicalFactory
from canonical.query import CanonicalRepository
from canonical.value_objects.code_location import CodeLocation


class TestPerformanceValidation:
    """Validate SC-001, SC-002 for performance."""
    
    def test_sc_001_reconstruction_under_5_seconds_for_2m_entities(self):
        """SC-001: Reconstruction <5s for 2M+ entities (1000 files, 1M symbols, 1M chunks, 10K relationships)"""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="perf_test", source_uri="https://github.com/perf", source="knowhere")
        
        # Create 2M+ entities (files, symbols, chunks, relationships)
        files = []
        symbols = []
        chunks = []
        relationships = []
        
        # Create 1000 files
        for i in range(1000):
            file = factory.build_file(
                repository_id=repo.id, 
                path=f"src/file_{i}.py", 
                checksum=f"checksum_{i}", 
                size_bytes=100 + i
            )
            files.append(file)
            
        # Create 1000 symbols per file (1M total)
        for i in range(1000):
            for j in range(1000):
                symbol = factory.build_symbol(
                    repository_id=repo.id, file_id=files[i].id,
                    name=f"func_{j}", qualified_name=f"module_{i}.func_{j}", kind="function",
                    location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
                )
                symbols.append(symbol)
                
        # Create 1000 chunks per file (1M total)
        for i in range(1000):
            for j in range(1000):
                chunk = factory.build_chunk(
                    repository_id=repo.id, file_id=files[i].id,
                    text=f"def func_{j}():\n    return {j}",
                    location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
                    chunk_type="code", ordering=j,
                )
                chunks.append(chunk)
                
        # Create 10 relationships per file (10K total)
        for i in range(1000):
            for j in range(10):
                if i * 10 + j < len(symbols):  # Make sure we don't exceed symbol count
                    rel = factory.build_relationship(
                        repository_id=repo.id, 
                        source_id=symbols[i * 10 + j].id, 
                        target_id=symbols[(i * 10 + j + 1) % len(symbols)].id, 
                        type="calls",
                    )
                    relationships.append(rel)
        
        # Measure time for reconstruction
        start_time = time.time()
        
        # Create repository with all entities
        perf_repo = CanonicalRepository(
            repository=repo,
            files=files,
            symbols=symbols,
            chunks=chunks,
            relationships=relationships
        )
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Verify reconstruction time is under 5 seconds
        assert total_time < 5.0, f"Reconstruction took {total_time:.2f}s, which exceeds 5s limit"
        
        # Verify we have the expected counts
        assert len(files) == 1000
        assert len(symbols) == 1000000  # 1000 files * 1000 symbols each
        assert len(chunks) == 1000000  # 1000 files * 1000 chunks each
        assert len(relationships) == 10000  # 1000 files * 10 relationships each
        
    def test_sc_002_cross_provider_semantic_hash_matching(self):
        """SC-002: Cross-provider semantic_hash and identifier matching"""
        factory = CanonicalFactory()
        repo1 = factory.build_repository(name="provider1", source_uri="https://github.com/provider1", source="provider1")
        repo2 = factory.build_repository(name="provider2", source_uri="https://github.com/provider2", source="provider2")
        
        # Create identical content in both repositories
        file1 = factory.build_file(repository_id=repo1.id, path="src/main.py", checksum="abc", size_bytes=100)
        file2 = factory.build_file(repository_id=repo2.id, path="src/main.py", checksum="def", size_bytes=100)
        
        # Create chunks with identical content (same semantic hash)
        chunk1 = factory.build_chunk(
            repository_id=repo1.id, file_id=file1.id,
            text="def process():\n    return True",
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
        )
        
        chunk2 = factory.build_chunk(
            repository_id=repo2.id, file_id=file2.id,
            text="def process():\n    return True",  # Same content
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
        )
        
        # Create repositories
        repo1_instance = CanonicalRepository(
            repository=repo1,
            files=[file1],
            symbols=[],
            chunks=[chunk1],
            relationships=[]
        )
        
        repo2_instance = CanonicalRepository(
            repository=repo2,
            files=[file2],
            symbols=[],
            chunks=[chunk2],
            relationships=[]
        )
        
        # Verify semantic hashes match for identical content
        assert chunk1.semantic_hash == chunk2.semantic_hash
        
        # Verify that the chunks have different IDs (different repositories)
        assert chunk1.id != chunk2.id
        
        # Verify that we can access both chunks
        retrieved_chunk1 = repo1_instance.get_chunk(chunk1.id)
        retrieved_chunk2 = repo2_instance.get_chunk(chunk2.id)
        
        assert retrieved_chunk1.semantic_hash == retrieved_chunk2.semantic_hash
        assert retrieved_chunk1.text == retrieved_chunk2.text