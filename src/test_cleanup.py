import os
import time
from .bot_controller import BotController
from .telegram_account import TelegramAccount
from .state_manager import StateManager

# --- Configuration for this specific test ---
TEST_ACCOUNT_NAME = "Telegram 001"

def run_cleanup_test():
    """
    Tests the pre-flight check logic in account.start().
    It expects a stale process for the TEST_ACCOUNT_NAME to be running manually.
    """
    print(f"--- Starting Stale Process Cleanup Test for {TEST_ACCOUNT_NAME} ---")
    print("This test expects you to have MANUALLY started this account's Telegram.exe")

    # 1. Minimal setup
    # We don't need a full controller, just enough for the account object to exist.
    dummy_controller = BotController(config=None, state_manager=StateManager(), test_mode=True)
    account_path = os.path.join("accounts", TEST_ACCOUNT_NAME)
    
    if not os.path.exists(account_path):
        print(f"Error: Test account path '{account_path}' not found.")
        return

    account = TelegramAccount(TEST_ACCOUNT_NAME, account_path, dummy_controller)
    
    try:
        # 2. Call start(), which should trigger the cleanup
        print(f"\n[{TEST_ACCOUNT_NAME}] Calling account.start()... Expecting it to find and kill the stale process.")
        if not account.start():
            print(f"[{TEST_ACCOUNT_NAME}] TEST FAILED: account.start() returned False.")
            return

        # 3. Find the window of the NEWLY launched process
        print(f"\n[{TEST_ACCOUNT_NAME}] Finding window of the newly launched process...")
        if not account.find_window():
            print(f"[{TEST_ACCOUNT_NAME}] TEST FAILED: Could not find the window for the new process.")
            return
        
        print(f"\nSUCCESS! The script successfully terminated the stale process, launched a new one, and found its window.")

    finally:
        # 4. Clean up the newly started process
        print(f"\n[{TEST_ACCOUNT_NAME}] Test finished. Stopping the new Telegram process...")
        account.stop()
        print(f"--- Cleanup Test for {TEST_ACCOUNT_NAME} FINISHED ---")

if __name__ == "__main__":
    run_cleanup_test()
