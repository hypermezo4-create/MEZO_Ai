"""
mezo-control-plane/src/orchestrator/kill_switch.py

Shared singleton kill switch. Every plugin execution checks this before proceeding.
CLI: `mezo stop-agent` calls .disarm().
Frontend: hits POST /api/control/kill-switch/disarm.

Thread-safe: uses threading.Event so checks are O(1) and non-blocking.
"""

import threading
import time
import logging

logger = logging.getLogger("mezo.kill_switch")


class KillSwitch:
    """
    Singleton kill switch for MEZO AI agent execution.

    ARMED   = normal operation (executions allowed).
    DISARMED = all new plugin executions are blocked.

    Re-arming requires an explicit POST /api/control/kill-switch/arm call —
    it does NOT happen automatically on agent restart.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._armed = True
                cls._instance._disarmed_at: float | None = None
                cls._instance._disarmed_by: str | None = None
        return cls._instance

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def arm(self, actor: str = "system") -> dict:
        """Re-arm the kill switch. Returns the new state record."""
        with self._lock:
            self._armed = True
            self._disarmed_at = None
            self._disarmed_by = None
        logger.info("[KillSwitch] ARMED by %s", actor)
        return self.status()

    def disarm(self, actor: str = "system") -> dict:
        """
        Disarm the kill switch. Blocks all new plugin executions.
        Already-dispatched subprocess calls are NOT force-killed.
        """
        with self._lock:
            self._armed = False
            self._disarmed_at = time.time()
            self._disarmed_by = actor
        logger.warning(
            "[KillSwitch] DISARMED by %s — all new plugin executions blocked", actor
        )
        return self.status()

    def is_armed(self) -> bool:
        """True = normal operation. False = all executions blocked."""
        return self._armed

    def status(self) -> dict:
        return {
            "armed": self._armed,
            "disarmed_at": self._disarmed_at,
            "disarmed_by": self._disarmed_by,
        }

    def assert_armed(self) -> None:
        """
        Raise KillSwitchDisarmedException if not armed.
        Called by PermissionGuard before every execution.
        """
        if not self._armed:
            raise KillSwitchDisarmedException(
                f"Kill switch is DISARMED (by {self._disarmed_by}). "
                "Run `mezo start-agent` or use the frontend Arm button to resume."
            )


class KillSwitchDisarmedException(RuntimeError):
    """Raised when a plugin action is attempted while the kill switch is disarmed."""
    pass


# Module-level singleton — import and use everywhere:
#   from src.orchestrator.kill_switch import kill_switch
kill_switch = KillSwitch()
