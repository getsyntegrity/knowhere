from typing import Any, List, Optional, Type, TypeVar
from uuid import uuid4
from sqlalchemy import ScalarResult
from unittest.mock import MagicMock

T = TypeVar("T")

class FakeScalarResult:
    def __init__(self, data: List[Any]):
        self._data = data

    def all(self) -> List[Any]:
        return list(self._data)

    def first(self) -> Optional[Any]:
        return self._data[0] if self._data else None

    def one_or_none(self) -> Optional[Any]:
        if not self._data:
            return None
        if len(self._data) > 1:
            raise Exception("Multiple results found")
        return self._data[0]
        
    def scalar_one_or_none(self) -> Optional[Any]:
        return self.one_or_none()

class FakeAsyncSession:
    """
    Stateful Fake Session that mimics AsyncSession behavior in memory.
    Stores objects in `self.storage` list.
    """
    def __init__(self):
        self.storage = []
        self.new = []
        self.deleted = []
        self.dirty = []
        
    def add(self, instance: Any):
        if not hasattr(instance, 'id') or instance.id is None:
            # Simulate ID generation on add/flush
            instance.id = str(uuid4())
            
        self.new.append(instance)
        # In a real session, 'add' attaches to session but commit persists.
        # For simplicity, we treat 'new' acting like 'pending'.
        
    async def commit(self):
        # Move new items to storage
        for item in self.new:
            if item not in self.storage:
                self.storage.append(item)
        self.new = []
        self.dirty = []
        self.deleted = []
        
    async def flush(self):
        # Assign IDs if missing (covered in add), basically no-op for memory fake
        pass
        
    async def refresh(self, instance: Any):
        # In memory, instance is the live object
        pass
        
    async def rollback(self):
        self.new = []
        self.dirty = []
        self.deleted = []
        
    async def execute(self, statement: Any):
        # Very basic query simulation.
        # This assumes statement is a simple select.
        # Real query parsing is hard, so we rely on finding types.
        
        # We look for the requested type in the statement if possible,
        # otherwise return everything that matches? 
        # This is the limitation of a Fake. 
        # For lightweight service tests, we often just want "get by ID" or "get all".
        
        # We can inspect the statement str or compiled form, but that's complex.
        # Strategy: For these lightweight tests, we can filter `self.storage`.
        # But `execute` returns a Result object.
        
        # Hack for simple "select(Model).where(Model.id == val)"
        # We will return ALL storage items wrapped in scalar result 
        # and let the caller filter? No, standard usage is `result.scalars().all()`.
        
        # If we need specific filtering, we can inject a "query engine" or
        # allow the test to pre-seed the return value if logic is too complex.
        # But we want STATEFUL behavior.
        
        # Let's try to infer target model from statement if currently possible.
        # If not, return full storage.
        
        # For the retained lightweight tests:
        # 1. API creates event: execute not called (only add/commit).
        # 2. Worker fetches event: `select(WebhookEvent).where(...)`.
        
        # Implementation: Simple scan of storage.
        results = []
        
        # Very naive filter: if we find an ID in the statement string that matches an object
        # but statement isn't a string usually.
        
        # Fallback: Return everything in storage. 
        # The code usually does `result.scalars().first()`. 
        # If we return everything, `one_or_none` might fail if multiple exist.
        
        # IMPROVEMENT: Inspect statement for `_where_criteria` (SQLAlchemy internal)
        # or just return a MagicMock that we configure per test if query is specific.
        
        # For these simplified test helpers:
        # We know we are looking up by ID.
        # Let's just return a generic FakeCursor that contains all items.
        # The application logic might filter it further? No, DB does filtering.
        
        # Let's simple check: if the statement has a `whereclause`?
        
        return MagicMock(scalars=lambda: FakeScalarResult(self.storage), scalar_one_or_none=lambda: self.storage[0] if self.storage else None)

    async def close(self):
        pass
        
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class FakeCeleryApp:
    def __init__(self):
        self.tasks = []
        
    def send_task(self, name, args=None, kwargs=None, **options):
        task_id = str(uuid4())
        self.tasks.append({
            "id": task_id,
            "name": name,
            "args": args or [],
            "kwargs": kwargs or {},
            "options": options
        })
        mock_task = MagicMock()
        mock_task.id = task_id
        return mock_task
