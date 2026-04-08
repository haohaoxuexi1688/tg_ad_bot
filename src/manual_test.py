import os
import sys
import time
from .bot_controller import BotController
from .telegram_account import TelegramAccount
from .state_manager import StateManager # Import StateManager

# --- Configuration for Manual Test ---
TEST_ACCOUNT_NAME = "Telegram 001" # Make sure this account exists in the 'accounts' folder
TEST_GROUP_LINK = "https://t.me/DGGX666"
GROUP_CAN_SEND_LINKS = False # Adjust based on your test group's settings

def run_manual_test():
    print(f"--- Starting Manual Integration Test for {TEST_ACCOUNT_NAME} ---")

    # 1. Initialize BotController in test mode
    # This prevents it from automatically discovering and managing multiple accounts
    state_manager = StateManager() # Create an instance of StateManager
    controller = BotController(config=None, state_manager=state_manager, test_mode=True)
    
    # Manually load data (messages, group_links) that the controller needs
    controller.load_data()
    # Add the test group link to the controller's group_links for get_wrapped_message
    if not any(g[0] == TEST_GROUP_LINK for g in controller.group_links):
        controller.group_links.append((TEST_GROUP_LINK, 0, GROUP_CAN_SEND_LINKS))


    # 2. Prepare the test account
    account_path = os.path.join("accounts", TEST_ACCOUNT_NAME)
    if not os.path.exists(account_path):
        print(f"Error: Test account path '{account_path}' not found. Please ensure '{TEST_ACCOUNT_NAME}' exists.")
        return

    account = TelegramAccount(TEST_ACCOUNT_NAME, account_path, controller)
    account.driver.debug_mode = True # Enable debug mode to save region screenshots
    controller.accounts.append(account) # Add to controller for state management

    # 3. Start the account
    print(f"[{TEST_ACCOUNT_NAME}] Launching Telegram...")
    if not account.start():
        print(f"[{TEST_ACCOUNT_NAME}] Failed to launch Telegram.")
        return
    
    # 4. Find window
    print(f"[{TEST_ACCOUNT_NAME}] Finding Telegram window...")
    if not account.find_window():
        print(f"[{TEST_ACCOUNT_NAME}] Failed to find Telegram window. Ensure it launched correctly.")
        account.stop()
        return

    # 5. Wait for account to be ready (using both GUI and log file check)
    print(f"[{TEST_ACCOUNT_NAME}] Waiting for Telegram client to be ready (GUI or Log)...")
    if not account.driver.wait_for_startup_screen(timeout=30):
        print(f"[{TEST_ACCOUNT_NAME}] Telegram client did not become ready. Stopping.")
        account.stop()
        return
    print(f"[{TEST_ACCOUNT_NAME}] Telegram client is ready.")

    # 6. Execute Join Group Flow
    print(f"\n[{TEST_ACCOUNT_NAME}] Initiating 'Join Group' flow for: {TEST_GROUP_LINK}")
    join_success = account.join_group_flow(TEST_GROUP_LINK)
    if join_success:
        print(f"[{TEST_ACCOUNT_NAME}] Successfully completed 'Join Group' flow.")
    else:
        print(f"[{TEST_ACCOUNT_NAME}] 'Join Group' flow FAILED.")
        # Decide if you want to proceed with send_ad_flow if join failed
        # For now, we'll continue to test send_ad_flow if join succeeded or failed
    
    # 7. Execute Send Ad Flow
    # Add a short delay between join and send ad to ensure UI stability
    time.sleep(5) 
    print(f"\n[{TEST_ACCOUNT_NAME}] Initiating 'Send Ad' flow for: {TEST_GROUP_LINK}")
    send_ad_success = account.send_ad_flow(TEST_GROUP_LINK, GROUP_CAN_SEND_LINKS)
    if send_ad_success:
        print(f"[{TEST_ACCOUNT_NAME}] Successfully completed 'Send Ad' flow.")
    else:
        print(f"[{TEST_ACCOUNT_NAME}] 'Send Ad' flow FAILED.")

    # 8. Clean up
    print(f"\n[{TEST_ACCOUNT_NAME}] Test completed. Stopping Telegram client...")
    account.stop()
    print(f"--- Manual Integration Test for {TEST_ACCOUNT_NAME} FINISHED ---")
    print("Please check the Telegram client to verify the actions.")

if __name__ == "__main__":
    run_manual_test()
