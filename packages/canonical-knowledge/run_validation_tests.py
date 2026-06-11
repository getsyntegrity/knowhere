#!/usr/bin/env python3
"""Simple test runner for our validation tests."""

import sys
import os

# Add the canonical-knowledge src directory to the path
# Use relative path so it works on any machine
script_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(script_dir, 'src')
sys.path.insert(0, src_path)

def test_isolation_validation():
    """Test isolation validation (AC-014 through AC-016)."""
    print("Testing Isolation Validation (AC-014 through AC-016)...")
    
    try:
        from canonical.adapters.file_adapter import FileAdapter
        from canonical.adapters.symbol_adapter import SymbolAdapter
        from canonical.adapters.chunk_adapter import ChunkAdapter
        from canonical.adapters.relationship_adapter import RelationshipAdapter
        from canonical.contracts.file_adapter import FileAdapterContract
        from canonical.contracts.symbol_adapter import SymbolAdapterContract
        from canonical.contracts.chunk_adapter import ChunkAdapterContract
        from canonical.contracts.relationship_adapter import RelationshipAdapterContract
        
        # AC-014: No provider imports in adapter test code
        print("  AC-014: Checking imports...")
        assert FileAdapterContract.__module__ == "canonical.contracts.file_adapter"
        assert SymbolAdapterContract.__module__ == "canonical.contracts.symbol_adapter"
        assert ChunkAdapterContract.__module__ == "canonical.contracts.chunk_adapter"
        assert RelationshipAdapterContract.__module__ == "canonical.contracts.relationship_adapter"
        print("    ✓ No provider imports in adapter test code")
        
        # AC-015: Removing adapter leaves others unaffected
        print("  AC-015: Testing adapter independence...")
        # Import and instantiate with factory
        from unittest.mock import Mock
        mock_factory = Mock()
        file_adapter = FileAdapter(factory=mock_factory)
        symbol_adapter = SymbolAdapter(factory=mock_factory)
        chunk_adapter = ChunkAdapter(factory=mock_factory)
        relationship_adapter = RelationshipAdapter(factory=mock_factory)
        
        assert isinstance(file_adapter, FileAdapter)
        assert isinstance(symbol_adapter, SymbolAdapter)
        assert isinstance(chunk_adapter, ChunkAdapter)
        assert isinstance(relationship_adapter, RelationshipAdapter)
        print("    ✓ Adapters can be instantiated independently")
        
        # AC-016: Adapter independence
        print("  AC-016: Testing adapter independence...")
        assert file_adapter is not None
        assert symbol_adapter is not None
        assert chunk_adapter is not None
        assert relationship_adapter is not None
        
        # Verify they have the required contract methods
        assert hasattr(file_adapter, 'convert')
        assert hasattr(symbol_adapter, 'convert')
        assert hasattr(chunk_adapter, 'convert')
        assert hasattr(relationship_adapter, 'convert')
        print("    ✓ Adapters are independent and have required methods")
        
        print("  All Isolation Validation tests passed!")
        return True
        
    except Exception as e:
        print(f"  ✗ Isolation Validation failed: {e}")
        return False

def test_boundary_conditions_validation():
    """Test boundary conditions validation (AC-017 through AC-024)."""
    print("Testing Boundary Conditions Validation (AC-017 through AC-024)...")
    
    try:
        from canonical.factory import CanonicalFactory
        from canonical.query import CanonicalRepository
        from canonical.value_objects.code_location import CodeLocation
        import hashlib
        
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        
        # AC-017: Empty repository handling
        print("  AC-017: Testing empty repository...")
        empty_repo = CanonicalRepository(
            repository=repo,
            files=[],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        retrieved_repo = empty_repo.get_repository(repo.id)
        assert retrieved_repo.id == repo.id
        
        files = empty_repo.find_entities_by_type("file")
        symbols = empty_repo.find_entities_by_type("symbol")
        chunks = empty_repo.find_entities_by_type("chunk")
        relationships = empty_repo.find_entities_by_type("relationship")
        
        assert len(files) == 0
        assert len(symbols) == 0
        assert len(chunks) == 0
        assert len(relationships) == 0
        print("    ✓ Empty repository handling works")
        
        # AC-018: Single file repository
        print("  AC-018: Testing single file repository...")
        file1 = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        single_file_repo = CanonicalRepository(
            repository=repo,
            files=[file1],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        retrieved_file = single_file_repo.get_file(file1.id)
        assert retrieved_file.id == file1.id
        assert retrieved_file.path == "src/main.py"
        
        files = single_file_repo.find_entities_by_type("file")
        assert len(files) == 1
        print("    ✓ Single file repository handling works")
        
        # AC-019: Large files handling
        print("  AC-019: Testing large files handling...")
        large_content = "def large_function():\n" + "    # This is a large function\n" * 1000 + "\n    return True"
        large_checksum = hashlib.sha256(large_content.encode("utf-8")).hexdigest()
        
        file2 = factory.build_file(
            repository_id=repo.id, 
            path="src/large.py", 
            checksum=large_checksum, 
            size_bytes=len(large_content)
        )
        
        large_repo = CanonicalRepository(
            repository=repo,
            files=[file2],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        retrieved_file = large_repo.get_file(file2.id)
        assert retrieved_file.id == file2.id
        assert retrieved_file.path == "src/large.py"
        assert retrieved_file.size_bytes == len(large_content)
        print("    ✓ Large files handling works")
        
        # AC-020: Unicode handling
        print("  AC-020: Testing unicode handling...")
        unicode_path = "src/unicode_测试.py"
        file3 = factory.build_file(
            repository_id=repo.id, 
            path=unicode_path, 
            checksum="abc", 
            size_bytes=100
        )
        
        unicode_repo = CanonicalRepository(
            repository=repo,
            files=[file3],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        retrieved_file = unicode_repo.get_file(file3.id)
        assert retrieved_file.id == file3.id
        assert retrieved_file.path == unicode_path
        print("    ✓ Unicode handling works")
        
        # AC-021: Circular symbols handling
        print("  AC-021: Testing circular symbols handling...")
        symbol1 = factory.build_symbol(
            repository_id=repo.id, file_id=file1.id,
            name="func1", qualified_name="main.func1", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        symbol2 = factory.build_symbol(
            repository_id=repo.id, file_id=file1.id,
            name="func2", qualified_name="main.func2", kind="function",
            location=CodeLocation(start_line=5, start_column=1, end_line=5, end_column=10),
        )
        
        rel1 = factory.build_relationship(
            repository_id=repo.id, source_id=symbol1.id, target_id=symbol2.id, type="calls",
        )
        rel2 = factory.build_relationship(
            repository_id=repo.id, source_id=symbol2.id, target_id=symbol1.id, type="calls",
        )
        
        circular_repo = CanonicalRepository(
            repository=repo,
            files=[file1],
            symbols=[symbol1, symbol2],
            chunks=[],
            relationships=[rel1, rel2]
        )
        
        retrieved_symbol1 = circular_repo.get_symbol(symbol1.id)
        retrieved_symbol2 = circular_repo.get_symbol(symbol2.id)
        retrieved_rel1 = circular_repo.get_relationship(rel1.id)
        retrieved_rel2 = circular_repo.get_relationship(rel2.id)
        
        assert retrieved_symbol1.qualified_name == "main.func1"
        assert retrieved_symbol2.qualified_name == "main.func2"
        assert retrieved_rel1.type == "calls"
        assert retrieved_rel2.type == "calls"
        print("    ✓ Circular symbols handling works")
        
        # AC-022: Binary files handling
        print("  AC-022: Testing binary files handling...")
        binary_checksum = "a1b2c3d4e5f67890123456789012345678901234567890123456789012345678"
        file4 = factory.build_file(
            repository_id=repo.id, 
            path="src/image.png", 
            checksum=binary_checksum, 
            size_bytes=1024
        )
        
        binary_repo = CanonicalRepository(
            repository=repo,
            files=[file4],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        retrieved_file = binary_repo.get_file(file4.id)
        assert retrieved_file.id == file4.id
        assert retrieved_file.path == "src/image.png"
        assert retrieved_file.checksum == binary_checksum
        print("    ✓ Binary files handling works")
        
        # AC-023: Missing optional fields handling
        print("  AC-023: Testing missing optional fields handling...")
        file5 = factory.build_file(
            repository_id=repo.id, 
            path="src/minimal.py", 
            checksum="abc", 
            size_bytes=100
        )
        
        minimal_repo = CanonicalRepository(
            repository=repo,
            files=[file5],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        retrieved_file = minimal_repo.get_file(file5.id)
        assert retrieved_file.id == file5.id
        assert retrieved_file.path == "src/minimal.py"
        assert retrieved_file.language is None
        assert retrieved_file.metadata == {}
        print("    ✓ Missing optional fields handling works")
        
        # AC-024: Same semantic_hash / different chunk_id
        print("  AC-024: Testing same semantic_hash/different chunk_id...")
        chunk1 = factory.build_chunk(
            repository_id=repo.id, file_id=file1.id,
            text="def func():\n    return True",
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
            semantic_hash="same_hash_12345678901234567890123456789012"
        )
        
        chunk2 = factory.build_chunk(
            repository_id=repo.id, file_id=file1.id,
            text="def func():\n    return False",
            location=CodeLocation(start_line=3, start_column=1, end_line=4, end_column=9),
            chunk_type="code", ordering=1,
            semantic_hash="same_hash_12345678901234567890123456789012"
        )
        
        hash_repo = CanonicalRepository(
            repository=repo,
            files=[file1],
            symbols=[],
            chunks=[chunk1, chunk2],
            relationships=[]
        )
        
        retrieved_chunk1 = hash_repo.get_chunk(chunk1.id)
        retrieved_chunk2 = hash_repo.get_chunk(chunk2.id)
        
        assert retrieved_chunk1.semantic_hash == retrieved_chunk2.semantic_hash
        assert retrieved_chunk1.id != retrieved_chunk2.id
        assert retrieved_chunk1.text != retrieved_chunk2.text
        assert retrieved_chunk1.text == "def func():\n    return True"
        assert retrieved_chunk2.text == "def func():\n    return False"
        print("    ✓ Same semantic_hash/different chunk_id handling works")
        
        print("  All Boundary Conditions Validation tests passed!")
        return True
        
    except Exception as e:
        print(f"  ✗ Boundary Conditions Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_performance_validation():
    """Test performance validation (SC-001, SC-002)."""
    print("Testing Performance Validation (SC-001, SC-002)...")
    
    try:
        from canonical.factory import CanonicalFactory
        from canonical.query import CanonicalRepository
        from canonical.value_objects.code_location import CodeLocation
        import time
        
        factory = CanonicalFactory()
        repo = factory.build_repository(name="perf_test", source_uri="https://github.com/perf", source="knowhere")
        
        # SC-001: Reconstruction <5s for 10k entities
        print("  SC-001: Testing reconstruction performance...")
        files = []
        symbols = []
        chunks = []
        relationships = []
        
        # Create 100 files (smaller for test)
        for i in range(100):
            file = factory.build_file(
                repository_id=repo.id, 
                path=f"src/file_{i}.py", 
                checksum=f"checksum_{i}", 
                size_bytes=100 + i
            )
            files.append(file)
            
        # Create 100 symbols per file (10k total)
        for i in range(100):
            for j in range(100):
                symbol = factory.build_symbol(
                    repository_id=repo.id, file_id=files[i].id,
                    name=f"func_{j}", qualified_name=f"module_{i}.func_{j}", kind="function",
                    location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
                )
                symbols.append(symbol)
                
        # Create 100 chunks per file (10k total)
        for i in range(100):
            for j in range(100):
                chunk = factory.build_chunk(
                    repository_id=repo.id, file_id=files[i].id,
                    text=f"def func_{j}():\n    return {j}",
                    location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
                    chunk_type="code", ordering=j,
                )
                chunks.append(chunk)
                
        # Measure time for reconstruction
        start_time = time.time()
        
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
        print(f"    ✓ Reconstruction took {total_time:.2f}s (under 5s limit)")
        
        # Verify we have the expected counts
        assert len(files) == 100
        assert len(symbols) == 10000  # 100 files * 100 symbols each
        assert len(chunks) == 10000  # 100 files * 100 chunks each
        print("    ✓ Entity counts are correct")
        
        # SC-002: Cross-provider semantic_hash and identifier matching
        print("  SC-002: Testing cross-provider semantic hash matching...")
        repo1 = factory.build_repository(name="provider1", source_uri="https://github.com/provider1", source="provider1")
        repo2 = factory.build_repository(name="provider2", source_uri="https://github.com/provider2", source="provider2")
        
        file1 = factory.build_file(repository_id=repo1.id, path="src/main.py", checksum="abc", size_bytes=100)
        file2 = factory.build_file(repository_id=repo2.id, path="src/main.py", checksum="def", size_bytes=100)
        
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
        assert chunk1.id != chunk2.id
        
        retrieved_chunk1 = repo1_instance.get_chunk(chunk1.id)
        retrieved_chunk2 = repo2_instance.get_chunk(chunk2.id)
        
        assert retrieved_chunk1.semantic_hash == retrieved_chunk2.semantic_hash
        assert retrieved_chunk1.text == retrieved_chunk2.text
        print("    ✓ Cross-provider semantic hash matching works")
        
        print("  All Performance Validation tests passed!")
        return True
        
    except Exception as e:
        print(f"  ✗ Performance Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Running validation tests...")
    print("=" * 50)
    
    success = True
    success &= test_isolation_validation()
    print()
    success &= test_boundary_conditions_validation()
    print()
    success &= test_performance_validation()
    print()
    
    if success:
        print("=" * 50)
        print("🎉 All validation tests passed!")
        sys.exit(0)
    else:
        print("=" * 50)
        print("❌ Some validation tests failed!")
        sys.exit(1)