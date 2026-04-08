import pytest
from unittest.mock import MagicMock, call
import pyautogui

from src.telegram_driver import TelegramDriver
from src.telegram_account import TelegramAccount

@pytest.fixture
def mock_account():
    account = MagicMock(spec=TelegramAccount)
    account.name = "mock_driver_account"
    account.activate_window.return_value = True
    account.controller = MagicMock()
    account.controller.state_manager = MagicMock()
    account.controller.get_wrapped_message.return_value = "mock ad message"
    
    account.window = MagicMock()
    account.window.left = 0
    account.window.top = 0
    account.window.width = 800
    account.window.height = 600
    
    return account

@pytest.fixture
def telegram_driver(mock_account):
    """Fixture to create a TelegramDriver with a mock account."""
    driver = TelegramDriver(mock_account)
    return driver

# Test Cases for the send_ad_flow

def test_send_ad_flow_success_with_checkmark(telegram_driver, mocker):
    """Happy Path 1: Sent by clicking button, confirmed with checkmark."""
    mocker.patch.object(telegram_driver, '_navigate_to_group_via_link', return_value="SUCCESS")
    mocker.patch('pyautogui.hotkey')
    mocker.patch.object(telegram_driver, 'wait_for_either_image', side_effect=[
        'input.png', # Step 1: UI is ready
        'send_dangou.png' # Step 3: Primary verification (checkmark)
    ])
    mocker.patch.object(telegram_driver, 'find_image', side_effect=[
        (10, 10), # For focus click
        (20, 20)  # For send button
    ])
    mock_click = mocker.patch('pyautogui.click')
    
    result = telegram_driver.send_ad_flow("https://t.me/testgroup", False)

    assert result == (True, "SUCCESS")
    telegram_driver.find_image.assert_any_call('send_button.png', timeout=2, confidence=0.9, region=(0, 0, 800, 600))
    mock_click.assert_any_call((20, 20)) # Asserts the send button was clicked

def test_send_ad_flow_success_with_enter_and_checkmark(telegram_driver, mocker):
    """Happy Path 2: Sent with Enter key, confirmed with checkmark."""
    mocker.patch.object(telegram_driver, '_navigate_to_group_via_link', return_value="SUCCESS")
    mocker.patch('pyautogui.hotkey')
    mocker.patch.object(telegram_driver, 'wait_for_either_image', side_effect=[
        'input.png', # Step 1: UI is ready
        'send_dangou.png' # Step 3: Primary verification (checkmark)
    ])
    mocker.patch.object(telegram_driver, 'find_image', side_effect=[
        (10, 10), # For focus click
        None      # For send button (not found)
    ])
    mock_press = mocker.patch('pyautogui.press')
    
    result = telegram_driver.send_ad_flow("https://t.me/testgroup", False)

    assert result == (True, "SUCCESS")
    mock_press.assert_any_call('enter') # Asserts Enter was pressed

def test_send_ad_flow_success_with_fallback(telegram_driver, mocker):
    """Happy Path 3: No checkmark, but success via send button disappearing (fallback)."""
    mocker.patch.object(telegram_driver, '_navigate_to_group_via_link', return_value="SUCCESS")
    mocker.patch('pyautogui.hotkey')
    mocker.patch.object(telegram_driver, 'wait_for_either_image', side_effect=[
        'input.png', # Step 1: UI is ready
        None       # Step 3: Primary verification (checkmark fails)
    ])
    # find_image for send button returns coords, wait_for_image for send button returns False (it's gone)
    mocker.patch.object(telegram_driver, 'find_image', return_value=(20, 20))
    mocker.patch.object(telegram_driver, 'wait_for_image', return_value=False)
    mocker.patch('pyautogui.click')
    
    result = telegram_driver.send_ad_flow("https://t.me/testgroup", False)

    assert result == (True, "SUCCESS")
    # Verify the fallback check was made in the specific region
    telegram_driver.wait_for_image.assert_called_with('send_button.png', timeout=2, confidence=0.9, region=(0, 0, 40, 40))

def test_send_ad_flow_failure_no_confirmation(telegram_driver, mocker):
    """Failure Path: No checkmark and fallback also fails (button still visible)."""
    mocker.patch.object(telegram_driver, '_navigate_to_group_via_link', return_value="SUCCESS")
    mocker.patch('pyautogui.hotkey')
    mocker.patch.object(telegram_driver, 'wait_for_either_image', side_effect=['input.png', None])
    # find_image for send button returns coords, wait_for_image for send button returns True (it's still there)
    mocker.patch.object(telegram_driver, 'find_image', return_value=(20, 20))
    mocker.patch.object(telegram_driver, 'wait_for_image', return_value=True) # Fallback fails
    
    result = telegram_driver.send_ad_flow("https://t.me/testgroup", False)
    
    assert result == (False, "FAILURE")

def test_send_ad_flow_failure_no_fallback_possible(telegram_driver, mocker):
    """Failure Path: No checkmark and no fallback possible (sent with Enter)."""
    mocker.patch.object(telegram_driver, '_navigate_to_group_via_link', return_value="SUCCESS")
    mocker.patch('pyautogui.hotkey')
    mocker.patch.object(telegram_driver, 'wait_for_either_image', side_effect=['input.png', None])
    # find_image for send button returns None
    mocker.patch.object(telegram_driver, 'find_image', side_effect=[(10,10), None])
    mock_wait_for_image = mocker.patch.object(telegram_driver, 'wait_for_image') # To check it's NOT called
    
    result = telegram_driver.send_ad_flow("https://t.me/testgroup", False)
    
    assert result == (False, "FAILURE")
    mock_wait_for_image.assert_not_called() # The fallback check should not even be attempted

def test_send_ad_flow_fail_to_get_ready(telegram_driver, mocker):
    """Test failure when the input box never appears, even after trying to join."""
    mocker.patch.object(telegram_driver, '_navigate_to_group_via_link', return_value="SUCCESS")
    mocker.patch('pyautogui.hotkey')
    mocker.patch.object(telegram_driver, 'wait_for_either_image', return_value=None)
    mocker.patch.object(telegram_driver, 'find_and_click', return_value=None) # for join button
    
    result = telegram_driver.send_ad_flow("https://t.me/testgroup", False)
    
    assert result == (False, "FAILURE")
    # Assert it tried to find the join button
    telegram_driver.find_and_click.assert_called_once_with('join_group.png', timeout=5, region=mocker.ANY)

def test_send_ad_flow_banned_on_rejoin_loop(telegram_driver, mocker):
    """
    Test the new logic where getting stuck on the join button triggers a BANNED status.
    """
    mocker.patch.object(telegram_driver, '_navigate_to_group_via_link', return_value="SUCCESS")
    mocker.patch('pyautogui.hotkey')
    mocker.patch.object(telegram_driver, 'wait_for_either_image', return_value=None)
    mocker.patch.object(telegram_driver, 'find_and_click', return_value=(1,1))
    mocker.patch.object(telegram_driver, 'wait_for_image', return_value=True)

    result = telegram_driver.send_ad_flow("https://t.me/stuck_group", False)

    assert result == (False, "BANNED")
    assert telegram_driver.wait_for_either_image.call_count == 3
    assert telegram_driver.find_and_click.call_count == 2
    telegram_driver.wait_for_image.assert_called_once_with('join_group.png', timeout=1, region=mocker.ANY)
    
# --- Kept old navigation tests as they are still valid ---

def test_navigate_to_group_banned_flow(telegram_driver, mocker):
    mocker.patch.object(telegram_driver, 'reset_to_task_start_state', return_value=True)
    mocker.patch.object(telegram_driver, 'go_to_saved_messages', return_value=True)
    mocker.patch.object(telegram_driver, 'find_and_click', return_value=(123, 456))
    mock_pyautogui_click = mocker.patch('pyautogui.click')
    mocker.patch('pyautogui.hotkey')
    mocker.patch('pyautogui.press')
    mocker.patch('pyperclip.copy')
    mocker.patch('time.sleep')
    mocker.patch.object(telegram_driver, 'wait_for_image', return_value=True)

    result = telegram_driver._navigate_to_group_via_link("https://t.me/bannedgroup")

    assert result == "BANNED"
    assert telegram_driver.wait_for_image.call_count == 2
    mock_pyautogui_click.assert_called_once_with((123, 456))

def test_navigate_to_group_false_positive_banned(telegram_driver, mocker):
    mocker.patch.object(telegram_driver, 'reset_to_task_start_state', return_value=True)
    mocker.patch.object(telegram_driver, 'go_to_saved_messages', return_value=True)
    mocker.patch.object(telegram_driver, 'find_and_click', return_value=(123, 456))
    mock_pyautogui_click = mocker.patch('pyautogui.click')
    mocker.patch('pyautogui.hotkey')
    mocker.patch('pyautogui.press')
    mocker.patch('pyperclip.copy')
    mocker.patch('time.sleep')
    mocker.patch.object(telegram_driver, 'wait_for_image', side_effect=[True, False])

    result = telegram_driver._navigate_to_group_via_link("https://t.me/flakygroup")

    assert result == "SUCCESS"
    assert telegram_driver.wait_for_image.call_count == 2
    mock_pyautogui_click.assert_called_once_with((123, 456))

def test_navigate_to_group_not_banned(telegram_driver, mocker):
    mocker.patch.object(telegram_driver, 'reset_to_task_start_state', return_value=True)
    mocker.patch.object(telegram_driver, 'go_to_saved_messages', return_value=True)
    mocker.patch.object(telegram_driver, 'find_and_click', return_value=(123, 456))
    mock_pyautogui_click = mocker.patch('pyautogui.click')
    mocker.patch('pyautogui.hotkey')
    mocker.patch('pyautogui.press')
    mocker.patch('pyperclip.copy')
    mocker.patch('time.sleep')
    mock_wait_for_image = mocker.patch.object(telegram_driver, 'wait_for_image', return_value=False)

    result = telegram_driver._navigate_to_group_via_link("https://t.me/goodgroup")

    assert result == "SUCCESS"
    mock_wait_for_image.assert_called_once_with('shoucang.png', timeout=2, region=(0, 0, 800, 600))
    mock_pyautogui_click.assert_not_called()