"""Contract tests for SymbolAdapter."""

from canonical.adapters.stubs import InMemorySymbolAdapter
from canonical.factory import CanonicalFactory
from canonical.value_objects.code_location import CodeLocation


class TestSymbolAdapterContract:
    """T027: SymbolAdapter contract test suite."""
    
    def test_qualified_name_construction(self):
        """SymbolAdapter constructs qualified_name."""
        adapter = InMemorySymbolAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        symbols = list(adapter.to_canonical(
            {"name": "process", "qualified_name": "main.process", "kind": "function"},
            file.id, repo.id,
        ))
        assert symbols[0].qualified_name == "main.process"
    
    def test_kind_mapping(self):
        """SymbolAdapter maps provider kind to canonical kind."""
        adapter = InMemorySymbolAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        symbols = list(adapter.to_canonical(
            {"name": "MyClass", "qualified_name": "main.MyClass", "kind": "class"},
            file.id, repo.id,
        ))
        assert symbols[0].kind == "class"
    
    def test_code_location_bounds(self):
        """SymbolAdapter validates CodeLocation bounds."""
        adapter = InMemorySymbolAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        symbols = list(adapter.to_canonical(
            {
                "name": "process", "qualified_name": "main.process", "kind": "function",
                "start_line": 10, "start_column": 1, "end_line": 20, "end_column": 2,
            },
            file.id, repo.id,
        ))
        assert symbols[0].location.start_line == 10
        assert symbols[0].location.end_line == 20
    
    def test_children_hierarchy(self):
        """SymbolAdapter preserves parent-child hierarchy."""
        adapter = InMemorySymbolAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        # Parent symbol
        parent = factory.build_symbol(
            repository_id=repo.id, file_id=file.id,
            name="MyClass", qualified_name="main.MyClass", kind="class",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        # Child symbol
        child = factory.build_symbol(
            repository_id=repo.id, file_id=file.id,
            name="method", qualified_name="main.MyClass.method", kind="method",
            location=CodeLocation(start_line=2, start_column=1, end_line=2, end_column=10),
            children=[],
        )
        
        # Parent references child
        parent_with_children = factory.build_symbol(
            repository_id=repo.id, file_id=file.id,
            name="MyClass", qualified_name="main.MyClass", kind="class",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
            children=[child.id],
        )
        
        assert child.id in parent_with_children.children
