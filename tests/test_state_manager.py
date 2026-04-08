import pytest
from unittest.mock import patch, MagicMock
import datetime

# It's better to import the class from the module
from src.state_manager import StateManager

# A fixture to create a fresh StateManager instance for each test
@pytest.fixture
def state_manager():
    # We can also mock the _load_state to prevent file IO during tests
    with patch.object(StateManager, '_load_state', return_value=None):
        manager = StateManager()
        # Initialize with an empty state for predictability
        manager.state = {
            "daily_stats": {},
            "joined_groups": {},
            "task_log": {},
            "task_failures": {}
        }
        yield manager

def test_get_account_daily_stats_new_account(state_manager):
    """Test that stats are created for a new account."""
    stats = state_manager.get_account_daily_stats("test_acc")
    today = datetime.date.today().isoformat()
    assert stats == {"date": today, "joins": 0, "sends": 0}
    assert state_manager.state["daily_stats"]["test_acc"] == stats

def test_get_account_daily_stats_reset_on_new_day(state_manager):
    """Test that stats are reset when the day changes."""
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    state_manager.state["daily_stats"]["test_acc"] = {"date": yesterday, "joins": 5, "sends": 10}
    
    stats = state_manager.get_account_daily_stats("test_acc")
    today = datetime.date.today().isoformat()
    assert stats == {"date": today, "joins": 0, "sends": 0}

def test_is_account_at_daily_limit(state_manager):
    """Test the daily limit checks."""
    state_manager.state["daily_stats"]["test_acc"] = {
        "date": datetime.date.today().isoformat(),
        "joins": 20,
        "sends": 400
    }
    assert state_manager.is_account_at_daily_limit("test_acc", "JOIN", daily_joins_limit=20, daily_sends_limit=400) == True
    assert state_manager.is_account_at_daily_limit("test_acc", "SEND_AD", daily_joins_limit=20, daily_sends_limit=400) == True
    assert state_manager.is_account_at_daily_limit("test_acc_2", "JOIN", daily_joins_limit=20, daily_sends_limit=400) == False

def test_update_account_daily_stats(state_manager):
    """Test that stats are correctly incremented."""
    with patch.object(state_manager, '_save_state') as mock_save:
        state_manager.update_account_daily_stats("test_acc", "JOIN")
        assert state_manager.state["daily_stats"]["test_acc"]["joins"] == 1
        mock_save.assert_called_once()
    
    with patch.object(state_manager, '_save_state') as mock_save:
        state_manager.update_account_daily_stats("test_acc", "SEND_AD")
        assert state_manager.state["daily_stats"]["test_acc"]["sends"] == 1
        mock_save.assert_called_once()


def test_group_cooldown_logic(state_manager, mocker):
    """Test the group cooldown logic."""
    account_name = "test_acc"
    group_link = "https://t.me/testgroup"
    
    # Test with no cooldown history
    assert state_manager.is_group_on_cooldown(account_name, group_link, 60)[0] == False

    # Mock datetime.now to control the time
    now = datetime.datetime.now()
    
    # Simulate that the last send was 30 minutes ago
    last_sent_time = now - datetime.timedelta(minutes=30)
    state_manager.state["task_log"][account_name] = {group_link: last_sent_time.isoformat()}
    
    # We need to mock datetime.datetime inside the 'datetime' module
    mock_dt = MagicMock()
    mock_dt.now.return_value = now
    mock_dt.fromisoformat.side_effect = datetime.datetime.fromisoformat
    mocker.patch('datetime.datetime', new=mock_dt)


    # Cooldown is 60 minutes, so it should be on cooldown
    assert state_manager.is_group_on_cooldown(account_name, group_link, 60)[0] == True
    # Cooldown is 20 minutes, so it should NOT be on cooldown
    assert state_manager.is_group_on_cooldown(account_name, group_link, 20)[0] == False

def test_failure_count_logic(state_manager):
    """Test the failure counting mechanism."""
    account = "test_acc"
    group = "test_group"

    assert state_manager.get_failure_count(account, group) == 0
    
    with patch.object(state_manager, '_save_state') as mock_save:
        state_manager.increment_failure_count(account, group)
        assert state_manager.get_failure_count(account, group) == 1
        mock_save.assert_called_once()

    with patch.object(state_manager, '_save_state') as mock_save:
        state_manager.increment_failure_count(account, group)
        assert state_manager.get_failure_count(account, group) == 2
        mock_save.assert_called_once()

    with patch.object(state_manager, '_save_state') as mock_save:
        state_manager.reset_failure_count(account, group)
        assert state_manager.get_failure_count(account, group) == 0
        mock_save.assert_called_once()

def test_is_account_in_group_logic(state_manager):
    """Test that is_account_in_group correctly checks joined_groups state."""
    account = "test_acc"
    group = "test_group"
    
    # Initially, account is not in the group
    assert state_manager.is_account_in_group(account, group) == False
    
    # Mark the group as joined
    with patch.object(state_manager, '_save_state') as mock_save:
        state_manager.mark_group_joined(account, group)
        mock_save.assert_called_once()
    
    # Now account should be in the group
    assert state_manager.is_account_in_group(account, group) == True

def test_account_level_banned_group_logic(state_manager):
    """Test the new account-level banned group logic."""
    acc1 = "acc1"
    acc2 = "acc2"
    group1 = "https://t.me/banned_for_acc1"
    group2 = "https://t.me/ok_group"

    # Ensure account_banned_in dict is initialized
    state_manager.state.setdefault("account_banned_in", {})

    # 1. Check groups that are not banned for anyone yet
    assert state_manager.is_group_banned_for_account(acc1, group1) == False
    assert state_manager.is_group_banned_for_account(acc2, group1) == False
    assert state_manager.is_group_banned_for_account(acc1, group2) == False

    # 2. Ban group1 for acc1 and verify
    with patch.object(state_manager, '_save_state') as mock_save:
        state_manager.add_banned_group_for_account(acc1, group1)
        # Verify it's banned for acc1
        assert state_manager.is_group_banned_for_account(acc1, group1) == True
        # Verify it's NOT banned for acc2
        assert state_manager.is_group_banned_for_account(acc2, group1) == False
        # Verify other groups are not affected for acc1
        assert state_manager.is_group_banned_for_account(acc1, group2) == False
        assert group1 in state_manager.state["account_banned_in"][acc1]
        mock_save.assert_called_once()

    # 3. Try to ban the same group again for the same account and verify no duplicates
    with patch.object(state_manager, '_save_state') as mock_save:
        state_manager.add_banned_group_for_account(acc1, group1)
        assert state_manager.state["account_banned_in"][acc1].count(group1) == 1
        mock_save.assert_not_called()
