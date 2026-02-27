"""
Redis ZSET-based concurrency semaphore.

Uses a Lua script for atomic acquire (prune zombies + check + add).
Release is a simple ZREM.
"""

import time

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import NoScriptError

from app.services.rate_limit.config import (
    MAX_JOB_DURATION_SECONDS,
    RATE_LIMIT_KEY_PREFIX,
)


class ConcurrencySemaphore:
    """
    Distributed concurrency limiter backed by a Redis sorted set.

    Each user gets a ZSET key. Members are job IDs scored by their
    acquisition timestamp. Zombie entries older than MAX_JOB_DURATION_SECONDS
    are pruned on every acquire attempt.
    """

    ACQUIRE_SCRIPT: str = """
local key = KEYS[1]
local max_concurrent = tonumber(ARGV[1])
local job_id = ARGV[2]
local now = tonumber(ARGV[3])
local max_duration = tonumber(ARGV[4])

-- Prune zombie entries older than max_duration
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - max_duration)

-- Check current count
local current = redis.call('ZCARD', key)
if current < max_concurrent then
    redis.call('ZADD', key, now, job_id)
    return 1
end
return 0
"""

    def __init__(self, key_prefix: str = RATE_LIMIT_KEY_PREFIX) -> None:
        self._key_prefix: str = key_prefix
        self._script_sha: str | None = None

    def _build_key(self, user_id: str) -> str:
        """Build the Redis key for a user's semaphore ZSET."""
        return f"{self._key_prefix}rate_limit:semaphore:{user_id}"

    async def acquire(
        self,
        redis: Redis,
        user_id: str,
        job_id: str,
        max_concurrent: int,
    ) -> bool:
        """
        Try to acquire a concurrency slot.

        Returns True if the slot was acquired, False if at capacity.
        """
        if max_concurrent == -1:
            return True

        key = self._build_key(user_id)
        now = time.time()
        args = [max_concurrent, job_id, now, MAX_JOB_DURATION_SECONDS]

        result = await self._eval_script(redis, key, args)
        acquired = result == 1

        if not acquired:
            logger.debug(
                f"Concurrency semaphore full for user={user_id}, "
                f"max={max_concurrent}"
            )
        return acquired

    async def release(
        self,
        redis: Redis,
        user_id: str,
        job_id: str,
    ) -> None:
        """Release a concurrency slot by removing the job from the ZSET."""
        key = self._build_key(user_id)
        await redis.zrem(key, job_id)

    async def _eval_script(
        self,
        redis: Redis,
        key: str,
        args: list,
    ) -> int:
        """
        Execute the Lua acquire script with evalsha/eval fallback.
        """
        if self._script_sha is not None:
            try:
                return await redis.evalsha(
                    self._script_sha, 1, key, *args
                )
            except NoScriptError:
                self._script_sha = None

        # Script not cached yet or was evicted -- load via EVAL
        result = await redis.eval(
            self.ACQUIRE_SCRIPT, 1, key, *args
        )
        # Cache the SHA for subsequent calls
        self._script_sha = await redis.script_load(self.ACQUIRE_SCRIPT)
        return result
