"""State-machine configuration."""

from dataclasses import dataclass
from typing import Dict


@dataclass
class StateMachineConfig:
    """State-machine settings."""

    max_retries: int = 3  # Maximum retry count.
    base_retry_delay: float = 0.1  # Base retry delay in seconds.

    # Timeout settings used with Redis Keyspace Notifications.
    state_timeouts: Dict[str, int] = None

    # Synchronization settings.
    sync_batch_size: int = 100  # Batch size for sync work.
    sync_interval: int = 300  # Sync interval in seconds.

    # Maintenance settings.
    maintenance_interval: int = 3600  # Maintenance interval in seconds.
    cleanup_interval: int = 1800  # Cleanup interval in seconds.

    # Redis Keyspace Notifications support.
    enable_keyspace_notifications: bool = True  # Enable Keyspace Notifications.

    def __post_init__(self) -> None:
        if self.state_timeouts is None:
            self.state_timeouts = {
                "pending": 300,  # 5 minutes
                "uploading": 600,  # 10 minutes
                "processing": 1800,  # 30 minutes
                "completed": 0,  # No timeout
                "failed": 0,  # No timeout
            }


# Default state-machine configuration.
DEFAULT_CONFIG = StateMachineConfig()


def get_state_machine_config() -> StateMachineConfig:
    """Return the active state-machine configuration."""
    return DEFAULT_CONFIG


def update_state_machine_config(**kwargs: object) -> StateMachineConfig:
    """Update and return the active state-machine configuration."""
    global DEFAULT_CONFIG
    DEFAULT_CONFIG = StateMachineConfig(**kwargs)
    return DEFAULT_CONFIG
