import os
import subprocess
import time
import datetime
from typing import Optional, Tuple

import psutil # For process management
import win32process # For finding window PID
import pygetwindow as gw # For window management

from .telegram_driver import TelegramDriver

class TelegramAccount:
    """Represents a single Telegram account session, launched and managed by the script."""
    def __init__(self, name: str, path: str, controller):
        self.name = name
        self.path = path
        self.exe_path = os.path.join(path, "Telegram.exe")
        self.controller = controller # Reference to the BotController for shared data/methods
        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.window: Optional[gw.Win32Window] = None
        self.status = "stopped" # stopped, starting, running, busy, resting, done_for_today
        self.last_action_time: datetime.datetime = datetime.datetime.now()
        self.ads_sent_in_current_round: set[str] = set() # Track groups that have successfully sent an ad in current round
        self.round_start_time: datetime.datetime = datetime.datetime.now() # To track rotation interval
        self.search_icon_coords: Optional[Tuple[int, int]] = None # New: Stores the fixed coordinates of the search icon
        self.driver = TelegramDriver(self)

    def start(self) -> bool:
        """
        Launches the Telegram.exe for this account, ensuring no stale processes are running.
        """
        if not os.path.exists(self.exe_path):
            print(f"[{self.name}] Error: Telegram.exe not found at {self.exe_path}")
            self.status = "error"
            return False

        # --- Pre-flight check for stale processes ---
        print(f"[{self.name}] Pre-flight check: Looking for stale processes from this account's directory...")
        cleaned_stale_process = False
        try:
            for p in psutil.process_iter(['pid', 'name', 'cwd']):
                try:
                    # Use os.path.samefile for robust path comparison
                    if p.info['name'] == 'Telegram.exe' and p.info['cwd'] and os.path.samefile(p.info['cwd'], self.path):
                        stale_pid = p.info['pid']
                        print(f"[{self.name}] Found stale process {stale_pid}. Attempting to terminate it forcefully.")
                        subprocess.run(f"taskkill /F /T /PID {stale_pid}", check=False, shell=True, capture_output=True)
                        cleaned_stale_process = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue # Ignore processes that disappear or we can't access
        except Exception as e:
            print(f"[{self.name}] Warning: Pre-flight check failed with an unexpected error: {e}")

        if cleaned_stale_process:
            print(f"[{self.name}] Stale process cleanup finished. Waiting a moment before launch...")
            time.sleep(3) # Give OS time to release file handles etc.

        # --- Original start logic ---
        try:
            print(f"[{self.name}] Launching with Popen from CWD: {self.path}...")
            self.process = subprocess.Popen([self.exe_path], cwd=self.path)
            self.pid = self.process.pid
            self.status = "starting"
            self.round_start_time = datetime.datetime.now() # Mark start time for rotation
            print(f"[{self.name}] Launched with PID: {self.pid}")
            return True
        except Exception as e:
            print(f"[{self.name}] Failed to launch with Popen: {e}")
            self.status = "error"
            return False

    def find_window(self) -> bool:
        """Finds and attaches the window corresponding to this account's PID."""
        if not self.pid:
            return False
        
        print(f"[{self.name}] Searching for window with PID {self.pid}...")
        for _ in range(30):
            try:
                if not psutil.pid_exists(self.pid):
                    print(f"[{self.name}] Error: Process with PID {self.pid} terminated unexpectedly.")
                    return False
                
                all_windows = gw.getAllWindows()
                for window in all_windows:
                    if not window.visible or not window.title:
                        continue
                    
                    _, w_pid = win32process.GetWindowThreadProcessId(window._hWnd)
                    if w_pid == self.pid:
                        self.window = window
                        self.status = "running"
                        print(f"[{self.name}] Successfully attached to window: '{self.window.title}'")
                        return True
            except Exception as e:
                print(f"[{self.name}] Error while searching for window: {e}")
            time.sleep(1)
        
        print(f"[{self.name}] Error: Could not find window for PID {self.pid} after 30 seconds.")
        self.status = "error"
        return False

    def stop(self, force: bool = False):
        """
        Terminates the process for this account, trying gracefully first (Ctrl+Q),
        then falling back to forceful termination (taskkill).
        """
        if self.pid and psutil.pid_exists(self.pid):
            try:
                # Attempt graceful shutdown first
                self.driver.quit_telegram()
                
                # Wait up to 5 seconds for the process to exit
                for i in range(5):
                    if not psutil.pid_exists(self.pid):
                        print(f"[{self.name}] Successfully terminated process {self.pid} gracefully.")
                        break
                    time.sleep(1)
                else: # This 'else' belongs to the 'for' loop, runs if loop completes without break
                    print(f"[{self.name}] Graceful quit failed. Falling back to forceful taskkill.")
                    raise subprocess.SubprocessError("Graceful quit timed out")

            except Exception as e:
                print(f"[{self.name}] Info: Graceful quit failed or was skipped ({e}). Using robust stop.")
                try:
                    kill_command = f"taskkill /F /T /PID {self.pid}"
                    subprocess.run(kill_command, check=True, shell=True, capture_output=True, text=True)
                    print(f"[{self.name}] Successfully terminated process tree for PID {self.pid}.")
                except subprocess.CalledProcessError as kill_e:
                    if "not found" in kill_e.stderr:
                        print(f"[{self.name}] Info: Process with PID {self.pid} was already closed.")
                    else:
                        print(f"[{self.name}] Error during taskkill for PID {self.pid}: {kill_e}")
                except Exception as final_e:
                    print(f"[{self.name}] An unexpected error occurred during termination of PID {self.pid}: {final_e}")

        self.status = "stopped"
        self.process = None
        self.pid = None
        self.window = None

    def activate_window(self):
        """Activates this account's window and brings it to the front."""
        if not self.window:
            print(f"[{self.name}] No window attached to activate.")
            return False
        try:
            if self.window.isMinimized:
                self.window.restore()
            self.window.activate()
            self.window.show()
            return True
        except Exception as e:
            error_msg = str(e)
            if "Error code from Windows: 0" in error_msg or "鎿嶄綔鎴愬姛瀹屾垚銆" in error_msg:
                return True
            else:
                print(f"[{self.name}] FATAL Error activating window: {e}")
                return False

    def wait_for_image(self, image_name: str, timeout: int = 30, confidence: float = 0.8) -> bool:
        return self.driver.wait_for_image(image_name, timeout, confidence)

    def join_group_flow(self, group_link: str) -> tuple[bool, str]:
        return self.driver.join_group_flow(group_link)

    def join_channel_flow(self, channel_link: str) -> tuple[bool, str]:
        return self.driver.join_channel_flow(channel_link)

    def send_ad_flow(self, group_link: str, group_can_send_links: bool) -> tuple[bool, str]:
        return self.driver.send_ad_flow(group_link, group_can_send_links)

