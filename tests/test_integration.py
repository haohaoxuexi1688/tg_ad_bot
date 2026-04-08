import pytest
from unittest.mock import MagicMock, PropertyMock, patch, call

from src.bot_controller import BotController
from src.telegram_account import TelegramAccount

class TestLoopExit(Exception):
    pass

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.concurrency = 3
    return config

@pytest.fixture
def mock_accounts():
    """Create 5 mock TelegramAccount objects."""
    accounts = []
    for i in range(1, 6):
        acc = MagicMock(spec=TelegramAccount)
        type(acc).name = PropertyMock(return_value=f"Acc{i:03d}")
        acc.status = "stopped"
        acc.pid = None
        acc.ads_sent_in_current_round = set()
        acc.window = MagicMock()
        acc.window.isMinimized = False
        acc.driver = MagicMock()
        accounts.append(acc)
    return accounts

def test_full_integration_flow(mock_config, mock_accounts, mocker):
    """
    Integration test for the BotController run loop.
    Simulates 5 accounts, 3 concurrency slots, and 3 groups.
    """
    # --- 1. Arrange and Mock ---
    mocker.patch('time.sleep')
    mocker.patch('psutil.pid_exists', return_value=True)
    mocker.patch.object(BotController, 'discover_accounts', return_value=None)
    mocker.patch.object(BotController, 'load_data', return_value=None)

    call_log = []
    tasks_processed = 0
    max_tasks = 15

    def mock_start(self):
        self.pid = int(self.name[-3:])
        self.status = "starting"
        self.status = "idle" 
        call_log.append(f"{self.name} started")
        return True
    
    def mock_stop(self):
        self.status = "stopped"
        self.pid = None
        call_log.append(f"{self.name} stopped")
        
    def mock_send_ad_flow(self, group_link, group_can_send_links):
        nonlocal tasks_processed
        tasks_processed += 1
        call_log.append(f"{self.name} sent ad to {group_link}")
        if tasks_processed >= max_tasks:
            raise TestLoopExit()
        return True, "SUCCESS"
        
    for acc in mock_accounts:
        acc.start.side_effect = mock_start.__get__(acc)
        acc.stop.side_effect = mock_stop.__get__(acc)
        acc.send_ad_flow.side_effect = mock_send_ad_flow.__get__(acc)
        acc.find_window.return_value = True
        acc.driver.wait_for_startup_screen.return_value = True

    # --- 2. Setup the Controller ---
    controller = BotController(mock_config, test_mode=True)
    controller.accounts = mock_accounts
    controller.group_links = [
        ("GroupA", 60, False, False), 
        ("GroupB", 60, False, False), 
        ("GroupC", 60, False, False)
    ]
    controller.state_manager = MagicMock()
    controller.state_manager.get_failure_count.return_value = 0
    controller.state_manager.is_account_in_group.return_value = True
    controller.state_manager.is_account_at_daily_limit.return_value = False
    controller.state_manager.is_group_on_cooldown.return_value = (False, "N/A", "N/A")
    controller.state_manager.is_group_banned.return_value = False
    controller.state_manager.is_group_banned_for_account.return_value = False
    
    # --- 3. Act ---
    try:
        controller.run()
    except TestLoopExit:
        print("Test loop finished gracefully.")

    # --- 4. Assert ---
    print("\n--- Call Log ---")
    for entry in call_log:
        print(entry)
    print("----------------\n")

    assert "Acc001 started" in call_log
    assert "Acc002 started" in call_log
    assert "Acc003 started" in call_log
    
    sent_to_A = len([c for c in call_log if "sent ad to GroupA" in c])
    sent_to_B = len([c for c in call_log if "sent ad to GroupB" in c])
    sent_to_C = len([c for c in call_log if "sent ad to GroupC" in c])
    
    assert sent_to_A > 0
    assert sent_to_B > 0
    assert sent_to_C > 0
    assert (sent_to_A + sent_to_B + sent_to_C) >= max_tasks

def test_proxy_check_is_run_for_all_concurrent_accounts(mock_config, mock_accounts, mocker):
    """
    Tests that each new account started to fill the concurrency pool is
    individually checked for readiness before being used.
    """
    # --- 1. Arrange and Mock ---
    mocker.patch('time.sleep')
    mocker.patch('psutil.pid_exists', return_value=True)
    mocker.patch.object(BotController, 'discover_accounts', return_value=None)
    mocker.patch.object(BotController, 'load_data', return_value=None)

    tasks_processed = 0
    max_tasks_for_exit = 1

    def mock_start(self):
        self.status = "idle"
        return True
    
    def mock_send_ad_flow(self, group_link, group_can_send_links):
        nonlocal tasks_processed
        tasks_processed += 1
        if tasks_processed >= max_tasks_for_exit:
            raise TestLoopExit()
        return True, "SUCCESS"

    for acc in mock_accounts:
        acc.start.side_effect = mock_start.__get__(acc)
        acc.send_ad_flow.side_effect = mock_send_ad_flow.__get__(acc)
        acc.find_window.return_value = True
        acc.driver.wait_for_startup_screen.return_value = True

    # --- 2. Setup the Controller ---
    controller = BotController(mock_config, test_mode=True)
    controller.accounts = mock_accounts[:3]
    controller.group_links = [("GroupA", 60, False, False)]
    controller.state_manager = MagicMock()
    controller.state_manager.get_failure_count.return_value = 0
    controller.state_manager.is_account_in_group.return_value = True
    controller.state_manager.is_account_at_daily_limit.return_value = False
    controller.state_manager.is_group_on_cooldown.return_value = (False, "N/A", "N/A")
    controller.state_manager.is_group_banned.return_value = False
    controller.state_manager.is_group_banned_for_account.return_value = False

    # --- 3. Act ---
    try:
        controller.run()
    except TestLoopExit:
        print("Test loop for proxy check finished gracefully.")

    # --- 4. Assert ---
    acc001, acc002, acc003 = mock_accounts[0], mock_accounts[1], mock_accounts[2]    
    acc001.driver.wait_for_startup_screen.assert_called_once_with(timeout=60)
    acc002.driver.wait_for_startup_screen.assert_called_once_with(timeout=60)
    acc003.driver.wait_for_startup_screen.assert_called_once_with(timeout=60)
    
    assert mock_accounts[3].driver.wait_for_startup_screen.call_count == 0
    assert mock_accounts[4].driver.wait_for_startup_screen.call_count == 0

    print("\nProxy Check Test Passed: Verified that 'wait_for_startup_screen' is called independently for each concurrent account.")
