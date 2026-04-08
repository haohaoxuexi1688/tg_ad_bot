import os
import json
import datetime
from typing import Dict, Any

STATE_FILE = os.path.join("results", "state.json")

class StateManager:
    """
    Manages all persistent state for the bot, reading from and writing to state.json.
    """
    def __init__(self):
        self.state: Dict = {}
        self._load_state()

    def _load_state(self):
        """Loads persistent state from state.json, ensuring backward compatibility."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
                print(f"Loaded state from {STATE_FILE}.")
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading or parsing {STATE_FILE}: {e}. Initializing new state.")
                self.state = {} # Start with an empty dict on error
        else:
            self.state = {}
            print(f"No {STATE_FILE} found, initializing new state.")

        # Ensure all required top-level keys exist to prevent KeyErrors with old state files.
        self.state.setdefault("daily_stats", {})
        self.state.setdefault("joined_groups", {})
        self.state.setdefault("task_log", {})
        self.state.setdefault("task_failures", {})
        self.state.setdefault("banned_groups", []) # Deprecated, but kept for backward compatibility
        self.state.setdefault("account_banned_in", {})
        self.state.setdefault("logged_out_accounts", [])

    def _save_state(self):
        """Saves current state to state.json."""
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving state to {STATE_FILE}: {e}")

    def get_account_daily_stats(self, account_name: str) -> Dict[str, Any]:
        """Gets or initializes daily stats for an account."""
        today = datetime.date.today().isoformat()
        stats = self.state["daily_stats"].setdefault(account_name, {"date": today, "joins": 0, "sends": 0})
        if stats["date"] != today: # Reset if new day
            stats = {"date": today, "joins": 0, "sends": 0}
            self.state["daily_stats"][account_name] = stats
        return stats

    def is_account_at_daily_limit(self, account_name: str, task_type: str, daily_joins_limit: int, daily_sends_limit: int) -> bool:
        """Checks if an account has hit its daily join/send limit."""
        stats = self.get_account_daily_stats(account_name)
        if task_type == "JOIN" and stats["joins"] >= daily_joins_limit:
            return True
        if task_type == "SEND_AD" and stats["sends"] >= daily_sends_limit:
            return True
        return False

    def update_account_daily_stats(self, account_name: str, task_type: str):
        """Increments daily join/send count for an account."""
        stats = self.get_account_daily_stats(account_name)
        if task_type == "JOIN":
            stats["joins"] += 1
        elif task_type == "SEND_AD":
            stats["sends"] += 1
        self.state["daily_stats"][account_name] = stats
        self._save_state()

    def is_group_on_cooldown(self, account_name: str, group_link: str, group_cooldown_minutes: int) -> tuple[bool, str, str]:
        """
        Checks if an account is on cooldown for a specific group.
        Returns a tuple: (is_on_cooldown, last_sent_timestamp, cooldown_end_time)
        """
        if group_cooldown_minutes == 0:
            return (False, "N/A", "N/A")
            
        task_log_for_account = self.state["task_log"].setdefault(account_name, {})
        last_sent_str = task_log_for_account.get(group_link)
        
        if last_sent_str:
            try:
                last_sent_time = datetime.datetime.fromisoformat(last_sent_str)
                cooldown_delta = datetime.timedelta(minutes=group_cooldown_minutes)
                cooldown_end_time = last_sent_time + cooldown_delta
                
                if datetime.datetime.now() < cooldown_end_time:
                    return (True, last_sent_str, cooldown_end_time.isoformat())
                else:
                    return (False, last_sent_str, cooldown_end_time.isoformat())
            except ValueError:
                 return (False, "Invalid Timestamp", "N/A") # Handle corrupted data
        
        return (False, "Not Sent Yet", "N/A")

    def update_group_last_sent_time(self, account_name: str, group_link: str):
        """Updates the last sent time for a group for a specific account."""
        self.state["task_log"].setdefault(account_name, {})[group_link] = datetime.datetime.now().isoformat()
        self._save_state()
        
    def mark_group_joined(self, account_name: str, group_link: str):
        """Marks a group as joined for a specific account."""
        if group_link not in self.state["joined_groups"].setdefault(account_name, []):
            self.state["joined_groups"].setdefault(account_name, []).append(group_link)
            self._save_state()

    def is_account_in_group(self, account_name: str, group_link: str) -> bool:
        """Checks if an account has previously joined this group/channel."""
        return group_link in self.state["joined_groups"].get(account_name, [])

    # --- Account-level ban logic ---
    def is_group_banned_for_account(self, account_name: str, group_link: str) -> bool:
        """Checks if a group is banned for a specific account."""
        return group_link in self.state["account_banned_in"].get(account_name, [])

    def add_banned_group_for_account(self, account_name: str, group_link: str):
        """Adds a group to the banned list for a specific account."""
        banned_list = self.state["account_banned_in"].setdefault(account_name, [])
        if group_link not in banned_list:
            banned_list.append(group_link)
            self._save_state()
            print(f"Added '{group_link}' to the ban list for account '{account_name}'.")

    # --- Deprecated global ban logic ---
    def is_group_banned(self, group_link: str) -> bool:
        """DEPRECATED: Checks if a group is in the permanently banned list."""
        return group_link in self.state.get("banned_groups", [])

    def add_banned_group(self, group_link: str):
        """DEPRECATED: Adds a group to the permanently banned list."""
        if group_link not in self.state.get("banned_groups", []):
            self.state.setdefault("banned_groups", []).append(group_link)
            self._save_state()
            print(f"Added '{group_link}' to the permanent ban list.")

    def get_failure_count(self, account_name: str, group_link: str) -> int:
        """Gets the current consecutive failure count for an account-group pair."""
        return self.state["task_failures"].get(account_name, {}).get(group_link, 0)


    def increment_failure_count(self, account_name: str, group_link: str):
        """Increments the failure count for an account-group pair."""
        failures = self.state["task_failures"].setdefault(account_name, {})
        failures[group_link] = failures.get(group_link, 0) + 1
        self._save_state()

    def reset_failure_count(self, account_name: str, group_link: str):
        """Resets the failure count for an account-group pair upon success."""
        if account_name in self.state["task_failures"]:
            if group_link in self.state["task_failures"][account_name]:
                del self.state["task_failures"][account_name][group_link]
                self._save_state()

    def mark_account_as_logged_out(self, account_name: str):
        """Adds an account to the list of logged-out accounts."""
        if account_name not in self.state["logged_out_accounts"]:
            self.state["logged_out_accounts"].append(account_name)
            self._save_state()
            print(f"Account '{account_name}' has been marked as logged out.")

    def is_account_logged_out(self, account_name: str) -> bool:
        """Checks if an account is in the logged-out list."""
        return account_name in self.state["logged_out_accounts"]
    
