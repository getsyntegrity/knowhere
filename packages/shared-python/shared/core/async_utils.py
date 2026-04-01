
import asyncio
from typing import TypeVar, Coroutine, Any

T = TypeVar("T")

def run_async_task(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run an async task in a synchronous context, reusing the event loop if possible.
    
    This function attempts to get the current event loop. If it's closed or missing,
    it creates a new one but DOES NOT close it after execution (unlike asyncio.run).
    This allows long-lived async resources to persist across tasks.
    
    Args:
        coro: The coroutine to run.
        
    Returns:
        The return value of the coroutine.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
             # Loop exists but closed - create new one
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
    except RuntimeError:
        # No loop in this thread - create new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)
