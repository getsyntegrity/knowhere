"""Test fixtures for canonical knowledge model."""

import pytest

from canonical.entities.chunk import Chunk
from canonical.entities.file import File
from canonical.entities.reference import Reference
from canonical.entities.relationship import Relationship
from canonical.entities.repository import Repository
from canonical.entities.symbol import Symbol
from canonical.factory import CanonicalFactory
from canonical.value_objects.code_location import CodeLocation


@pytest.fixture
def factory():
    """CanonicalFactory instance."""
    return CanonicalFactory()


@pytest.fixture
def repo(factory):
    """A basic Repository fixture."""
    return factory.build_repository(
        name="test-repo",
        source_uri="https://github.com/test/repo",
        source="knowhere",
    )


@pytest.fixture
def file(factory, repo):
    """A basic File fixture."""
    return factory.build_file(
        repository_id=repo.id,
        path="src/main.py",
        checksum="abc123",
        size_bytes=100,
        language="python",
    )


@pytest.fixture
def symbol(factory, repo, file):
    """A basic Symbol fixture."""
    return factory.build_symbol(
        repository_id=repo.id,
        file_id=file.id,
        name="process_data",
        qualified_name="main.process_data",
        kind="function",
        location=CodeLocation(start_line=10, start_column=1, end_line=20, end_column=2),
    )


@pytest.fixture
def chunk(factory, repo, file):
    """A basic Chunk fixture."""
    return factory.build_chunk(
        repository_id=repo.id,
        file_id=file.id,
        text="def process_data():\n    pass",
        location=CodeLocation(start_line=10, start_column=1, end_line=11, end_column=9),
        chunk_type="code",
        ordering=0,
    )


@pytest.fixture
def relationship(factory, repo, symbol):
    """A basic Relationship fixture."""
    return factory.build_relationship(
        repository_id=repo.id,
        source_id=symbol.id,
        target_id=symbol.id,
        type="calls",
    )


@pytest.fixture
def reference(factory, repo, file, symbol):
    """A basic Reference fixture."""
    return factory.build_reference(
        repository_id=repo.id,
        source_id=file.id,
        target_id=symbol.id,
        source_file_id=file.id,
        target_file_id=file.id,
        location=CodeLocation(start_line=15, start_column=5, end_line=15, end_column=17),
        role="call",
    )
