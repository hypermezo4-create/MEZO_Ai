"""
Tests for kill_switch.py
Run: python mezo-control-plane/tests/test_kill_switch.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.orchestrator.kill_switch import KillSwitch, KillSwitchDisarmedException

def reset_singleton():
    """Force the singleton to reset between tests."""
    KillSwitch._instance = None

def test_armed_by_default():
    reset_singleton()
    ks = KillSwitch()
    assert ks.is_armed(), "Kill switch should be armed by default"
    print("[OK] test_armed_by_default")

def test_disarm_blocks_execution():
    reset_singleton()
    ks = KillSwitch()
    ks.disarm(actor="test")
    assert not ks.is_armed(), "Kill switch should be disarmed after .disarm()"
    try:
        ks.assert_armed()
        assert False, "Should have raised KillSwitchDisarmedException"
    except KillSwitchDisarmedException:
        pass
    print("[OK] test_disarm_blocks_execution")

def test_rearm_allows_execution():
    reset_singleton()
    ks = KillSwitch()
    ks.disarm(actor="test")
    ks.arm(actor="test")
    assert ks.is_armed(), "Kill switch should be armed after .arm()"
    ks.assert_armed()  # should not raise
    print("[OK] test_rearm_allows_execution")

def test_status_tracks_actor():
    reset_singleton()
    ks = KillSwitch()
    ks.disarm(actor="cli_command")
    status = ks.status()
    assert status["armed"] is False
    assert status["disarmed_by"] == "cli_command"
    assert status["disarmed_at"] is not None
    print("[OK] test_status_tracks_actor")

def test_singleton_shared_state():
    reset_singleton()
    ks1 = KillSwitch()
    ks2 = KillSwitch()
    ks1.disarm(actor="test")
    assert ks2.is_armed() is False, "Both instances should share state (singleton)"
    print("[OK] test_singleton_shared_state")

if __name__ == "__main__":
    test_armed_by_default()
    test_disarm_blocks_execution()
    test_rearm_allows_execution()
    test_status_tracks_actor()
    test_singleton_shared_state()
    print("\n[PASS] All kill_switch tests passed!")
