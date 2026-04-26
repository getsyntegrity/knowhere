"""State-machine configuration."""

from dataclasses import dataclass, field
from typing import Dict


DEFAULT_STATE_TIMEOUTS: Dict[str, int] = {
    "pending": 300,
    "uploading": 600,
    "processing": 1800,
    "completed": 0,
    "failed": 0,
}


@dataclass
class StateMachineConfig:
    """State-machine settings."""

    max_retries: int = 3  # Maximum retry count.
    base_retry_delay: float = 0.1  # Base retry delay in seconds.

    # Timeout settings used with Redis Keyspace Notifications.
    state_timeouts: Dict[str, int] = field(
        default_factory=lambda: DEFAULT_STATE_TIMEOUTS.copy()
    )

    # Synchronization settings.
    sync_batch_size: int = 100  # Batch size for sync work.
    sync_interval: int = 300  # Sync interval in seconds.

    # Maintenance settings.
    maintenance_interval: int = 3600  # Maintenance interval in seconds.
    cleanup_interval: int = 1800  # Cleanup interval in seconds.

    # Redis Keyspace Notifications support.
    enable_keyspace_notifications: bool = True  # Enable Keyspace Notifications.

# Default state-machine configuration.
DEFAULT_CONFIG = StateMachineConfig()


def get_state_machine_config() -> StateMachineConfig:
    """Return the active state-machine configuration."""
    return DEFAULT_CONFIG


def update_state_machine_config(
    *,
    max_retries: int | None = None,
    base_retry_delay: float | None = None,
    state_timeouts: Dict[str, int] | None = None,
    sync_batch_size: int | None = None,
    sync_interval: int | None = None,
    maintenance_interval: int | None = None,
    cleanup_interval: int | None = None,
    enable_keyspace_notifications: bool | None = None,
) -> StateMachineConfig:
    """Update and return the active state-machine configuration."""
    global DEFAULT_CONFIG
    current = DEFAULT_CONFIG
    DEFAULT_CONFIG = StateMachineConfig(
        max_retries=current.max_retries if max_retries is None else max_retries,
        base_retry_delay=(
            current.base_retry_delay
            if base_retry_delay is None
            else base_retry_delay
        ),
        state_timeouts=(
            current.state_timeouts.copy()
            if state_timeouts is None
            else state_timeouts
        ),
        sync_batch_size=(
            current.sync_batch_size if sync_batch_size is None else sync_batch_size
        ),
        sync_interval=current.sync_interval if sync_interval is None else sync_interval,
        maintenance_interval=(
            current.maintenance_interval
            if maintenance_interval is None
            else maintenance_interval
        ),
        cleanup_interval=(
            current.cleanup_interval if cleanup_interval is None else cleanup_interval
        ),
        enable_keyspace_notifications=(
            current.enable_keyspace_notifications
            if enable_keyspace_notifications is None
            else enable_keyspace_notifications
        ),
    )
    return DEFAULT_CONFIG
