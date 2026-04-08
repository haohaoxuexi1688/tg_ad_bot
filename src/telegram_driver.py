import os
import time
import random
import re
import pyperclip
from datetime import datetime
from typing import List, Optional, Tuple # Added List, Optional and Tuple

import pyautogui

class AccountLoggedOutException(Exception):
    """Custom exception raised when an account is detected to be logged out."""
    pass

class TelegramDriver:
    """
    This class encapsulates all the GUI automation logic using pyautogui.
    It provides a high-level API for interacting with the Telegram UI,
    prioritizing keyboard shortcuts for stability.
    """
    def __init__(self, account):
        self.account = account
        self.debug_dir = os.path.join("results", "debug_screenshots")
        self.debug_mode = False 
        os.makedirs(self.debug_dir, exist_ok=True)

    # --- Screenshot and Helper Methods ---
    def _save_debug_screenshot(self, outcome: str, image_name: str, region: Optional[Tuple[int, int, int, int]] = None):
        """Saves a screenshot for debugging, either full screen or a specific region."""
        if not self.debug_mode:
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        image_name_safe = image_name.replace('.png', '').replace('\\', '_').replace('/', '_')
        
        # Add a suffix if it's a regional screenshot
        region_suffix = "_region" if region else ""
        screenshot_path = os.path.join(self.debug_dir, f"{outcome}_{timestamp}_{self.account.name}_{image_name_safe}{region_suffix}.png")
        
        try:
            # Pass region to screenshot function if it exists
            pyautogui.screenshot(screenshot_path, region=region)
            print(f"[{self.account.name}] DEBUG: Saved {outcome} screenshot to {screenshot_path}")
        except Exception as e:
            print(f"[{self.account.name}] DEBUG: Failed to save screenshot: {e}")

    def wait_for_image(self, image_name: str, timeout: int = 5, confidence: float = 0.8, region: Optional[Tuple[int, int, int, int]] = None) -> bool:
        """Waits for a specific image to appear on screen, optionally in a specific region."""
        image_path = os.path.join("data", "images", image_name)
        if not os.path.exists(image_path):
            print(f"[{self.account.name}] GUI Error: Image file not found at {image_path}")
            return False

        if region:
            self._save_debug_screenshot("SEARCH_AREA", image_name, region=region)

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if pyautogui.locateOnScreen(image_path, confidence=confidence, region=region):
                    print(f"[{self.account.name}] Found signal '{image_name}'.")
                    self._save_debug_screenshot("SUCCESS_wait_for", image_name, region=region)
                    return True
            except pyautogui.PyAutoGUIException:
                pass
            time.sleep(1)
        
        print(f"[{self.account.name}] Timeout: Could not find '{image_name}'.")
        self._save_debug_screenshot("FAIL_wait_for", image_name, region=region)
        return False

    def wait_for_either_image(self, image_names: List[str], timeout: int = 5, confidence: float = 0.8, region: Optional[Tuple[int, int, int, int]] = None) -> Optional[str]:
        """Waits for any one of a list of images to appear on screen, optionally in a specific region."""
        if region:
            self._save_debug_screenshot("SEARCH_AREA_EITHER", " ".join(image_names), region=region)
            
        start_time = time.time()
        while time.time() - start_time < timeout:
            for image_name in image_names:
                image_path = os.path.join("data", "images", image_name)
                if not os.path.exists(image_path):
                    continue
                try:
                    if pyautogui.locateOnScreen(image_path, confidence=confidence, region=region):
                        print(f"[{self.account.name}] Found signal '{image_name}'.")
                        self._save_debug_screenshot("SUCCESS_wait_for", image_name, region=region)
                        return image_name
                except pyautogui.PyAutoGUIException:
                    pass
            time.sleep(1)

        image_list_str = ", ".join(image_names)
        print(f"[{self.account.name}] Timeout: Could not find any of '{image_list_str}'.")
        self._save_debug_screenshot("FAIL_wait_for_either", image_list_str.replace(', ','_'), region=region)
        return None

    def find_and_click(self, image_name: str, timeout: int = 5, confidence: float = 0.8, region: Optional[Tuple[int, int, int, int]] = None) -> Optional[tuple]:
        """Finds an image on screen (optionally in a specific region) and clicks it."""
        image_path = os.path.join("data", "images", image_name)
        if not os.path.exists(image_path):
            return None
        
        # Save a debug screenshot of the search region if specified
        if region:
            self._save_debug_screenshot("SEARCH_AREA", image_name, region=region)

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                coords = pyautogui.locateCenterOnScreen(image_path, confidence=confidence, region=region)
                if coords:
                    self._save_debug_screenshot("SUCCESS_find_click", image_name, region=region)
                    pyautogui.click(coords)
                    return coords
            except pyautogui.PyAutoGUIException:
                pass
            time.sleep(0.2)
        
        self._save_debug_screenshot("FAIL_find_click", image_name, region=region)
        return None

    # --- Core Action Primitives (New Refactored Logic) ---

    def wait_for_startup_screen(self, timeout: int = 10) -> bool:
        """
        Checks for the initial startup screen. It first looks for 'chushi.png'.
        If not found, it checks for 'tuichu.png' to detect a logged-out state.
        Raises AccountLoggedOutException if the account is logged out.
        """
        print(f"[{self.account.name}] Action: Waiting for startup screen ('chushi.png')...")
        if self.wait_for_image('chushi.png', timeout=timeout):
            return True

        # If chushi.png is not found, check if it's because the account is logged out
        print(f"[{self.account.name}] '{'chushi.png'}' not found. Checking for logged-out state...")
        if self.wait_for_image('tuichu.png', timeout=2):
            raise AccountLoggedOutException("Account is logged out (tuichu.png detected).")
        if self.wait_for_image('logout.png', timeout=2):
            raise AccountLoggedOutException("Account is logged out (logout.png detected).")

        return False

    def reset_to_task_start_state(self) -> bool:
        """
        Ensures the UI is in a usable initial state for a task. Prioritizes checking for
        'input.png' (in-chat view). If not found, presses ESC three times
        and then checks for 'chushi.png' (main view). All checks are inside the window.
        """
        print(f"[{self.account.name}] Action: Resetting to task start state (prioritizing input box)...")
        window = self.account.window
        if not window: return False
        window_region = (window.left, window.top, window.width, window.height)
        
        # Ensure window is activated
        self.account.activate_window()
        time.sleep(0.3)
        
        # First, check if account is logged out
        if self.wait_for_image('logout.png', timeout=2, region=window_region):
            print(f"[{self.account.name}]   - DETECTED: Account is logged out (logout.png). Aborting task.")
            raise AccountLoggedOutException("Account logged out during task.")
        
        if self.wait_for_image('input.png', timeout=5, region=window_region):
            print(f"[{self.account.name}]   - Already in a usable task state (chat view).")
            return True

        print(f"[{self.account.name}]   - Input box not found. Pressing ESC 3 times to return to main view.")
        for _ in range(3):
            pyautogui.press('esc')
            time.sleep(0.5)
            # Check for logout after each ESC
            if self.wait_for_image('logout.png', timeout=1, region=window_region):
                print(f"[{self.account.name}]   - DETECTED: Account is logged out (logout.png). Aborting task.")
                raise AccountLoggedOutException("Account logged out during task.")

        if self.wait_for_image('chushi.png', timeout=5, region=window_region):
            print(f"[{self.account.name}]   - Successfully returned to main view.")
            return True

        print(f"[{self.account.name}]   - FAILURE: Could not reset to a recognized task start state.")
        return False

    def go_to_saved_messages(self) -> bool:
        """Navigates to 'Saved Messages' using Ctrl+0 and verifies."""
        print(f"[{self.account.name}] Action: Navigating to Saved Messages...")
        window = self.account.window
        if not window: return False
        window_region = (window.left, window.top, window.width, window.height)
        
        # Ensure window is activated before sending hotkey
        self.account.activate_window()
        time.sleep(0.5)
        
        pyautogui.hotkey('ctrl', '0')
        time.sleep(2)  # Give more time for the view to switch

        # Try multiple times to find the saved messages indicator
        for attempt in range(3):
            if self.wait_for_image('shoucang.png', timeout=3, region=window_region):
                print(f"[{self.account.name}]   - Successfully navigated to Saved Messages.")
                return True
            if attempt < 2:
                print(f"[{self.account.name}]   - Retry {attempt+1}/3: Waiting for Saved Messages...")
                time.sleep(2)
        
        # Even if we can't verify, Ctrl+0 usually works. Continue with warning.
        print(f"[{self.account.name}]   - WARNING: Could not verify 'shoucang.png', but Ctrl+0 was sent. Proceeding...")
        return True

    def find_image(self, image_name: str, timeout: int = 5, confidence: float = 0.8, region: Optional[tuple] = None) -> Optional[tuple]:
        """Finds an image on screen and returns its center coordinates, but does not click."""
        image_path = os.path.join("data", "images", image_name)
        if not os.path.exists(image_path):
            return None
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                coords = pyautogui.locateCenterOnScreen(image_path, confidence=confidence, region=region)
                if coords:
                    return coords
            except pyautogui.PyAutoGUIException:
                pass
            time.sleep(0.2)
        return None

    def quit_telegram(self):
        """Attempts to quit Telegram gracefully using Ctrl+Q."""
        print(f"[{self.account.name}] Action: Attempting graceful quit (Ctrl+Q)...")
        if self.account.window:
            self.account.activate_window()
            pyautogui.hotkey('ctrl', 'q')
    
    # --- Unified Navigation Flow ---

    def _navigate_to_group_via_link(self, group_link: str) -> str:
        """
        A unified private method to navigate to a group by posting its link in Saved Messages.
        Returns "SUCCESS", "FAILURE", or "BANNED".
        """
        if not self.reset_to_task_start_state():
            return "FAILURE"
        
        if not self.go_to_saved_messages():
            return "FAILURE"
        
        print(f"[{self.account.name}] Pasting group link in Saved Messages...")
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        time.sleep(0.5)
        pyperclip.copy(group_link)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        pyautogui.press('enter')
        time.sleep(4)

        window = self.account.window
        if not window: return "FAILURE"
        
        region_height = 250
        search_region = (window.left, window.top + window.height - region_height, window.width, region_height)

        print(f"[{self.account.name}] Attempting to click 'View Group' button in region {search_region}...")
        view_group_coords = self.find_and_click('view_group.png', timeout=5, region=search_region)
        if not view_group_coords:
            print(f"[{self.account.name}]   - FAILURE: Could not find 'view_group.png' button in the specified region.")
            print(f"[{self.account.name}]   - FALLBACK: Searching full screen for 'view_group.png'.")
            view_group_coords = self.find_and_click('view_group.png', timeout=2)
            if not view_group_coords:
                print(f"[{self.account.name}]   - FAILURE: Could not find 'view_group.png' button on full screen either.")
                return "FAILURE"

        print(f"[{self.account.name}]   - Clicked 'view_group.png'. Waiting for group view to load...")
        time.sleep(3)

        # --- Banned Group Check ---
        window_region = (window.left, window.top, window.width, window.height)
        if self.wait_for_image('shoucang.png', timeout=2, region=window_region):
            print(f"[{self.account.name}]   - WARNING: Detected 'shoucang.png' after first click. Possible banned group. Retrying click...")
            pyautogui.click(view_group_coords) # Retry the click
            time.sleep(3)
            if self.wait_for_image('shoucang.png', timeout=2, region=window_region):
                print(f"[{self.account.name}]   - CONFIRMED BANNED: 'shoucang.png' still visible after second click.")
                return "BANNED"
            else:
                print(f"[{self.account.name}]   - Second click seemed to work. Proceeding with caution.")
        
        return "SUCCESS"

    # --- Public-Facing High-Level Flows ---

    def join_group_flow(self, group_link: str) -> tuple[bool, str]:
        """
        Executes the full GUI flow to join a single group.
        Returns a tuple: (success, reason) where reason is "SUCCESS", "FAILURE", or "BANNED".
        """
        print(f"\n[{self.account.name}] Starting 'Join Group' flow for: {group_link}")
        if not self.account.activate_window(): return (False, "FAILURE")
        
        navigation_status = self._navigate_to_group_via_link(group_link)
        if navigation_status != "SUCCESS":
            return (False, navigation_status) # Propagate "FAILURE" or "BANNED"

        window = self.account.window
        if not window: return (False, "FAILURE")
        window_region = (window.left, window.top, window.width, window.height)

        print(f"[{self.account.name}] In group view, attempting to find and click 'join_group.png'...")
        if self.find_and_click('join_group.png', timeout=5, region=window_region):
            print(f"[{self.account.name}] Clicked the 'Join Group' button.")
            time.sleep(3)
        else:
            print(f"[{self.account.name}] Info: Could not find 'join_group.png'. Assuming already in group.")
        
        if self.wait_for_either_image(['input.png', 'send_button.png'], timeout=5, region=window_region):
            print(f"[{self.account.name}] SUCCESS: 'Join Group' task is complete (input box or send button is visible).")
            self.account.controller.state_manager.mark_group_joined(self.account.name, group_link)
            return (True, "SUCCESS")
        else:
            if self.wait_for_image('join_group.png', timeout=1, region=window_region):
                print(f"[{self.account.name}] FAILURE: 'Join Group' task failed (input box not visible, and 'join_group.png' still present). Account may be restricted.")
            else:
                print(f"[{self.account.name}] FAILURE: 'Join Group' task failed (input box is NOT visible).")
            return (False, "FAILURE")

    def join_channel_flow(self, channel_link: str) -> tuple[bool, str]:
        """
        Executes the full GUI flow to join a channel.
        Returns a tuple: (success, reason) where reason is "SUCCESS", "FAILURE", or "BANNED".
        
        Difference from join_group_flow:
        - Uses 'view_channel.png' instead of 'view_group.png'
        - Uses 'join_channel.png' instead of 'join_group.png'
        - Verifies success by checking for 'mute.png' (channel mute button)
        - Channels are read-only, no input box check needed
        """
        print(f"\n[{self.account.name}] Starting 'Join Channel' flow for: {channel_link}")
        if not self.account.activate_window(): 
            return (False, "FAILURE")
        
        # Step 1: Navigate to channel via link in Saved Messages
        if not self.reset_to_task_start_state():
            return (False, "FAILURE")
        
        if not self.go_to_saved_messages():
            return (False, "FAILURE")
        
        print(f"[{self.account.name}] Pasting channel link in Saved Messages...")
        import pyperclip
        pyperclip.copy(channel_link)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        pyautogui.press('enter')
        time.sleep(4)

        window = self.account.window
        if not window: 
            return (False, "FAILURE")
        
        # Step 2: Click 'View Channel' button
        region_height = 250
        search_region = (window.left, window.top + window.height - region_height, window.width, region_height)

        print(f"[{self.account.name}] Attempting to click 'view_channel.png'...")
        view_coords = self.find_and_click('view_channel.png', timeout=5, region=search_region)
        if not view_coords:
            view_coords = self.find_and_click('view_channel.png', timeout=2)
            if not view_coords:
                print(f"[{self.account.name}] FAILURE: Could not find 'view_channel.png'.")
                return (False, "FAILURE")

        print(f"[{self.account.name}] Clicked 'view_channel.png'. Waiting for channel view to load...")
        time.sleep(3)

        # Step 3: Click 'Join Channel' button
        window_region = (window.left, window.top, window.width, window.height)
        print(f"[{self.account.name}] Looking for 'join_channel.png'...")
        
        if self.find_and_click('join_channel.png', timeout=5, region=window_region):
            print(f"[{self.account.name}] Clicked 'join_channel.png'.")
            time.sleep(2)
        else:
            print(f"[{self.account.name}] Info: Could not find 'join_channel.png'. Checking if already in channel...")

        # Step 4: Verify success by checking for mute.png
        print(f"[{self.account.name}] Verifying channel join by checking for 'mute.png'...")
        if self.wait_for_image('mute.png', timeout=5, region=window_region):
            print(f"[{self.account.name}] SUCCESS: 'Join Channel' task complete (mute.png found).")
            self.account.controller.state_manager.mark_group_joined(self.account.name, channel_link)
            return (True, "SUCCESS")
        else:
            # Check if join button is still there (indicating failure)
            if self.wait_for_image('join_channel.png', timeout=1, region=window_region):
                print(f"[{self.account.name}] FAILURE: 'join_channel.png' still visible after click.")
                return (False, "FAILURE")
            else:
                print(f"[{self.account.name}] WARNING: Could not verify channel join (no mute.png), but join button is gone.")
                # Assume success if join button is gone
                self.account.controller.state_manager.mark_group_joined(self.account.name, channel_link)
                return (True, "SUCCESS")

    def send_ad_flow(self, group_link: str, group_can_send_links: bool) -> tuple[bool, str]:
        """
        Executes the full GUI flow to send an ad to a group.
        Returns a tuple: (success, reason) where reason is "SUCCESS", "FAILURE", or "BANNED".
        """
        print(f"\n[{self.account.name}] Starting 'Send Ad' flow for: {group_link}")
        if not self.account.activate_window(): return (False, "FAILURE")
        
        navigation_status = self._navigate_to_group_via_link(group_link)
        if navigation_status != "SUCCESS":
            return (False, navigation_status) # Propagate "FAILURE" or "BANNED"

        window = self.account.window
        if not window: return (False, "FAILURE")
        window_region = (window.left, window.top, window.width, window.height)
        
        # --- Step 1: Ensure UI is ready to send message (input box is visible) ---
        is_ready_to_send = self.wait_for_either_image(['input.png', 'send_button.png'], timeout=5, region=window_region)

        if not is_ready_to_send:
            print(f"[{self.account.name}] Info: No input/send button immediately visible. Checking for 'join_group.png'...")
            if self.find_and_click('join_group.png', timeout=5, region=window_region):
                print(f"[{self.account.name}] Clicked 'join_group.png'. Waiting for input box...")
                time.sleep(3)
                is_ready_to_send = self.wait_for_either_image(['input.png', 'send_button.png'], timeout=5, region=window_region)

                # NEW BAN LOGIC: If input box is STILL not there, check if we are stuck on the join button
                if not is_ready_to_send:
                    print(f"[{self.account.name}] Still no input box. Checking if join button is stuck...")
                    if self.wait_for_image('join_group.png', timeout=1, region=window_region):
                        print(f"[{self.account.name}] 'join_group.png' is still visible. Retrying click once...")
                        self.find_and_click('join_group.png', timeout=1, region=window_region)
                        time.sleep(3)
                        if not self.wait_for_either_image(['input.png', 'send_button.png'], timeout=5, region=window_region):
                            print(f"[{self.account.name}] CONFIRMED BANNED: Still no input box after retry. Account is likely restricted from joining.")
                            return (False, "BANNED")
            else:
                print(f"[{self.account.name}] FAILURE: Cannot find 'join_group.png'. Aborting ad send.")
                return (False, "FAILURE")
        
        if not is_ready_to_send:
            print(f"[{self.account.name}] FAILURE: Could not get to a state with an input box even after trying to join. Aborting ad send.")
            return (False, "FAILURE")
        
        # --- Step 2: UI is ready, proceed with typing and sending ---
        print(f"[{self.account.name}] Ready to send ad (input box found).")
        
        # --- START FOCUS ENHANCEMENT ---
        # Explicitly click the input area to ensure focus before typing.
        # We prioritize 'input.png' as it's the most direct target.
        input_box_coords = self.find_image('input.png', timeout=1, region=window_region)
        if input_box_coords:
            print(f"[{self.account.name}] Clicking input box to ensure focus.")
            pyautogui.click(input_box_coords)
            time.sleep(0.3)
        # --- END FOCUS ENHANCEMENT ---
        
        print(f"[{self.account.name}] Clearing input box before sending ad...")
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')

        ad_message = self.account.controller.get_wrapped_message(group_can_send_links)
        print(f"[{self.account.name}] Typing ad message: '{ad_message}'")
        pyperclip.copy(ad_message)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        
        print(f"[{self.account.name}] Attempting to send ad message...")
        
        send_button_region = None
        # Use a slightly larger confidence for finding the button we intend to click and track
        send_button_coords = self.find_image('send_button.png', timeout=2, confidence=0.9, region=window_region)

        if send_button_coords:
            # Create a small region around the button to check for its disappearance
            button_width = 40
            button_height = 40
            send_button_region = (
                int(send_button_coords[0] - button_width / 2),
                int(send_button_coords[1] - button_height / 2),
                button_width,
                button_height
            )
            print(f"[{self.account.name}] Found send button at {send_button_coords}. Clicking it.")
            pyautogui.click(send_button_coords)
        else:
            print(f"[{self.account.name}] Could not find 'send_button.png', falling back to pressing Enter.")
            pyautogui.press('enter')

        print(f"[{self.account.name}] Verifying send status...")

        # --- Primary Verification: Checkmark ---
        region_height = 250
        bottom_search_region = (window.left, window.top + window.height - region_height, window.width, region_height)
        sent_status_image = self.wait_for_either_image(['send_dangou.png', 'send_shuanggou.png'], timeout=5, region=bottom_search_region)

        if sent_status_image:
            print(f"[{self.account.name}] SUCCESS: Ad message sent confirmed by checkmark '{sent_status_image}'.")
            return (True, "SUCCESS")

        # --- Fallback Verification: Send button disappeared from its original location ---
        if send_button_region:
            print(f"[{self.account.name}] No checkmark found. Trying fallback: checking if send button disappeared from its original region.")
            # Use a short timeout to see if it's gone
            if not self.wait_for_image('send_button.png', timeout=2, confidence=0.9, region=send_button_region):
                print(f"[{self.account.name}] SUCCESS: Send button is gone from its original location. Message likely sent successfully (fallback).")
                return (True, "SUCCESS")
            else:
                print(f"[{self.account.name}] Fallback failed: Send button is still visible in its original location.")

        # --- Final Failure ---
        print(f"[{self.account.name}] FAILURE: No send confirmation (neither checkmark nor button disappearance).")
        self._save_debug_screenshot("FAIL_SEND_CONFIRMATION", "no_confirmation", region=window_region)
        return (False, "FAILURE")
