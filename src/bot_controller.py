import os
import sys
import json
import datetime
import random
import time
from threading import Lock
from typing import List, Dict, Optional, Tuple, Any

import psutil

from .telegram_account import TelegramAccount
from .state_manager import StateManager
from .telegram_driver import AccountLoggedOutException

# --- Constants and Configuration ---
DAILY_JOINS_LIMIT = 20
DAILY_SENDS_LIMIT = 400
# Long cycle rest after an account finishes a round (in minutes)
ACCOUNT_ROUND_REST_MIN_MINUTES = 5
ACCOUNT_ROUND_REST_MAX_MINUTES = 30
# Account rotation interval (how often to replace old accounts with new ones in the active pool)
# This is a fallback if an account never hits "done_for_today" or "round_complete_cooldown"
ACCOUNT_ROTATION_INTERVAL_MINUTES = 60
# How many times a task can fail for a specific account-group pair before it's skipped for a while.
FAILURE_THRESHOLD = 1


class BotController:
    """Manages all accounts and the main botting logic."""
    def __init__(self, config=None, state_manager=None, test_mode=False):
        self.config = config
        self.accounts: List[TelegramAccount] = []
        self.messages: List[str] = []
        self.group_links: List[Tuple[str, int, bool, bool]] = []  # (link, cooldown, can_send_links, is_channel)
        self.contacts: List[str] = []
        self.state_manager = state_manager if state_manager is not None else StateManager()
        self.gui_lock = Lock()
        
        if not test_mode:
            print("Starting Bot Controller...")
            self.load_data()
            if self.state_manager:
                self._synchronize_state()

    def discover_accounts(self):
        """Discovers Telegram accounts based on directory structure."""
        accounts_root = "accounts"
        if not os.path.exists(accounts_root):
            print(f"Error: Accounts directory '{accounts_root}' not found.")
            return

        for account_name in os.listdir(accounts_root):
            account_path = os.path.join(accounts_root, account_name)
            if os.path.isdir(account_path) and account_name.startswith("Telegram"):
                if os.path.exists(os.path.join(account_path, "Telegram.exe")):
                    self.accounts.append(TelegramAccount(account_name, account_path, self))
                    print(f"Discovered account: {account_name} at {account_path}")
                else:
                    print(f"Skipping directory '{account_name}': Telegram.exe not found inside.")
        if not self.accounts:
            print(f"Warning: No valid Telegram accounts found in '{accounts_root}'.")

    def load_data(self):
        """Loads messages, group links, and contacts from respective data files."""
        # Load messages
        messages_path = os.path.join("data", "messages.txt")
        if os.path.exists(messages_path):
            with open(messages_path, 'r', encoding='utf-8') as f:
                self.messages = [line.strip() for line in f if line.strip()]
            print(f"Loaded {len(self.messages)} messages from {messages_path}.")
        else:
            print(f"Warning: Messages file '{messages_path}' not found.")

        # Load group/channel links
        # Format: link,cooldown_minutes,can_send_links,is_channel
        # is_channel: true for channel, false or empty for group
        # Lines starting with # are treated as comments
        grouplist_path = os.path.join("data", "grouplist.txt")
        if os.path.exists(grouplist_path):
            with open(grouplist_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue  # Skip empty lines and comments
                    parts = line.split(',')
                    if len(parts) >= 2 and parts[1].strip().isdigit():
                        group_link = parts[0].strip()
                        cooldown_minutes = int(parts[1].strip())
                        can_send_links = False
                        is_channel = False
                        if len(parts) >= 3 and parts[2].strip().lower() == 'true':
                            can_send_links = True
                        if len(parts) >= 4 and parts[3].strip().lower() == 'true':
                            is_channel = True
                        self.group_links.append((group_link, cooldown_minutes, can_send_links, is_channel))
                    else:
                        # If the format is invalid or cooldown is not specified, default to 0 and warn the user.
                        print(f"[Warning] Invalid format in grouplist.txt on line {i+1}: '{line}'. Defaulting cooldown to 0.")
                        self.group_links.append((parts[0].strip(), 0, False, False)) 
            print(f"Loaded {len(self.group_links)} group/channel links from {grouplist_path}.")
        else:
            print(f"Warning: Group list file '{grouplist_path}' not found.")
        
        # Load contacts
        contacts_path = os.path.join("data", "contacts.txt")
        if os.path.exists(contacts_path):
            with open(contacts_path, 'r', encoding='utf-8') as f:
                self.contacts = [line.strip() for line in f if line.strip()]
            print(f"Loaded {len(self.contacts)} contacts from {contacts_path}.")
        else:
            print(f"Warning: Contacts file '{contacts_path}' not found.")

    def get_wrapped_message(self, group_can_send_links: bool) -> str:
        """
        Returns a random message, wrapped with random leading/trailing spaces and a random contact name.
        The 'group_can_send_links' parameter can be used to select messages appropriate for link-sending groups.
        """
        if not self.messages:
            base_message = "**No message configured.**"
        else:
            base_message = f"**{random.choice(self.messages)}**"
        
        leading_spaces = " " * random.randint(0, 3)
        
        if self.contacts:
            random_contact_raw = random.choice(self.contacts)
            if group_can_send_links:
                final_contact = random_contact_raw
            else:
                final_contact = f"`{random_contact_raw}`"
            wrapped_message = f"{leading_spaces}{base_message} {final_contact}" 
        else:
            wrapped_message = f"{leading_spaces}{base_message}"

        return wrapped_message

    def _get_next_group_task_for_account(self, account: TelegramAccount) -> Optional[Tuple[str, int, bool, bool, str]]:
        """
        Finds the next group/channel task (JOIN or SEND_AD) for an account to process in its current round.
        Returns: (link, cooldown_minutes, can_send_links, is_channel, task_type)
        """
        shuffled_groups = list(self.group_links)
        random.shuffle(shuffled_groups)
        
        for group_link, cooldown_minutes, group_can_send_links, is_channel in shuffled_groups:
            # --- Start Enhanced Logging ---
            print(f"    [{account.name}] Evaluating group: {group_link}")

            # Check if the group is permanently banned for this account
            if self.state_manager.is_group_banned_for_account(account.name, group_link):
                print(f"    [{account.name}] -> Skipping: Group is in the ban list for this account.")
                continue
            
            # Check if failure threshold for this group has been exceeded
            # Note: Skip this check if config has skip_failure_check=True (for join-only modes)
            if not getattr(self.config, 'skip_failure_check', False):
                if self.state_manager.get_failure_count(account.name, group_link) >= FAILURE_THRESHOLD:
                    print(f"    [{account.name}] -> Skipping: Failure threshold ({FAILURE_THRESHOLD}) exceeded for this group.")
                    continue

            if group_link in account.ads_sent_in_current_round:
                print(f"    [{account.name}] -> Skipping: Already sent in this round.")
                continue 

            is_in_group = self.state_manager.is_account_in_group(account.name, group_link)
            
            if is_in_group:
                is_on_cooldown, last_sent, cooldown_end_time = self.state_manager.is_group_on_cooldown(account.name, group_link, cooldown_minutes)
                
                print(f"    [{account.name}] -> Cooldown check: Config={cooldown_minutes}m, LastSent={last_sent}, CooldownEnds={cooldown_end_time}")

                if self.state_manager.is_account_at_daily_limit(account.name, "SEND_AD", DAILY_JOINS_LIMIT, DAILY_SENDS_LIMIT):
                    print(f"    [{account.name}] -> Skipping: Account is at its daily send limit.")
                    continue

                if is_on_cooldown:
                    print(f"    [{account.name}] -> Skipping: Group is on cooldown.")
                    continue

                print(f"    [{account.name}] -> DECISION: Assigning SEND_AD task.")
                return (group_link, cooldown_minutes, group_can_send_links, is_channel, "SEND_AD")
            
            else: # Not in group
                if self.state_manager.is_account_at_daily_limit(account.name, "JOIN", DAILY_JOINS_LIMIT, DAILY_SENDS_LIMIT):
                    print(f"    [{account.name}] -> Skipping: Account is at its daily join limit.")
                    continue
                
                print(f"    [{account.name}] -> DECISION: Assigning JOIN task.")
                # For channels, use JOIN_CHANNEL task type
                if is_channel:
                    return (group_link, cooldown_minutes, group_can_send_links, is_channel, "JOIN_CHANNEL")
                else:
                    return (group_link, cooldown_minutes, group_can_send_links, is_channel, "JOIN")

        print(f"    [{account.name}] -> No suitable tasks found in this round.")
        return None
    
    def _synchronize_state(self):
        """
        Removes stale group/channel data from the state file.
        If a group/channel was removed from grouplist.txt, its corresponding entries
        in task_log and task_failures will be deleted.
        """
        print("Synchronizing state with grouplist.txt...")
        valid_groups = {g[0] for g in self.group_links}
        
        # --- Clean up task_log ---
        task_log = self.state_manager.state.get("task_log", {})
        stale_accounts_in_log = []
        for account, group_logs in task_log.items():
            stale_groups = [g for g in group_logs if g not in valid_groups]
            for g in stale_groups:
                print(f"    - Removing stale group '{g}' from task_log for account '{account}'")
                del group_logs[g]
            if not group_logs: # If account has no group logs left
                stale_accounts_in_log.append(account)
        
        # Clean up accounts that have no logs left
        for acc in stale_accounts_in_log:
            del task_log[acc]

        # --- Clean up task_failures ---
        task_failures = self.state_manager.state.get("task_failures", {})
        stale_accounts_in_failures = []
        for account, group_failures in task_failures.items():
            stale_groups = [g for g in group_failures if g not in valid_groups]
            for g in stale_groups:
                print(f"    - Removing stale group '{g}' from task_failures for account '{account}'")
                del group_failures[g]
            if not group_failures:
                stale_accounts_in_failures.append(account)

        for acc in stale_accounts_in_failures:
            del task_failures[acc]

        # --- Clean up joined_groups ---
        joined_groups = self.state_manager.state.get("joined_groups", {})
        stale_accounts_in_joined = []
        for account, groups in joined_groups.items():
            stale_groups = [g for g in groups if g not in valid_groups]
            for g in stale_groups:
                print(f"    - Removing stale group '{g}' from joined_groups for account '{account}'")
                groups.remove(g)
            if not groups:
                stale_accounts_in_joined.append(account)
        
        for acc in stale_accounts_in_joined:
            del joined_groups[acc]

        # --- Clean up account_banned_in ---
        account_banned_in = self.state_manager.state.get("account_banned_in", {})
        stale_accounts_in_banned = []
        for account, banned_list in account_banned_in.items():
            stale_groups = [g for g in banned_list if g not in valid_groups]
            for g in stale_groups:
                print(f"    - Removing stale group '{g}' from account_banned_in for account '{account}'")
                banned_list.remove(g)
            if not banned_list:
                stale_accounts_in_banned.append(account)
        
        for acc in stale_accounts_in_banned:
            del account_banned_in[acc]

        # --- Clean up banned_groups ---
        banned_groups = self.state_manager.state.get("banned_groups", [])
        stale_banned_groups = [g for g in banned_groups if g not in valid_groups]
        if stale_banned_groups:
            print(f"    - Removing stale groups from banned_groups: {', '.join(stale_banned_groups)}")
            self.state_manager.state["banned_groups"] = [g for g in banned_groups if g not in stale_banned_groups]

        self.state_manager._save_state()
        print("State synchronization complete.")

    def run(self):
        """Main execution loop implementing the dynamic rotation concurrent pool."""
        self.discover_accounts()
        
        if not self.accounts or not self.group_links:
            print("Cannot start without accounts and group links. Exiting.")
            sys.exit(1)
        
        current_active_accounts: List[TelegramAccount] = []

        while True:
            now = datetime.datetime.now()
            
            # This is the main account cleanup and rotation logic
            accounts_to_remove = []
            for acc in current_active_accounts:
                # Reason 1: Account has been stopped manually (e.g. end of round)
                if acc.status == "stopped":
                    accounts_to_remove.append(acc)
                    continue

                # Reason 2: Process died unexpectedly
                if acc.pid and not psutil.pid_exists(acc.pid):
                    print(f"[{acc.name}] Process {acc.pid} died unexpectedly. Marking for removal.")
                    acc.stop() # Ensure status is set to 'stopped'
                    accounts_to_remove.append(acc)
                    continue

                # Reason 3: Account has been running for too long (rotation)
                if (now - acc.round_start_time).total_seconds() > ACCOUNT_ROTATION_INTERVAL_MINUTES * 60:
                    print(f"[{acc.name}] Reached rotation interval. Terminating for rotation.")
                    acc.stop()
                    accounts_to_remove.append(acc)
                    continue
                
                # Reason 4: Account has sent an ad to every single group in this round
                if acc.status == "idle" and len(acc.ads_sent_in_current_round) >= len(self.group_links):
                    print(f"[{acc.name}] Completed a full round (all ads sent). Terminating for rotation.")
                    acc.stop()
                    accounts_to_remove.append(acc)
                    continue

            if accounts_to_remove:
                for acc in accounts_to_remove:
                    if acc in current_active_accounts:
                        current_active_accounts.remove(acc)
                    
                    # Move the account to the end of the queue for rotation
                    if acc in self.accounts:
                        self.accounts.remove(acc)
                        self.accounts.append(acc)
                print(f"Rotated/Removed accounts. Active pool size: {len(current_active_accounts)}. New account queue order starts with: {self.accounts[0].name if self.accounts else 'N/A'}")

            # This loop tries to fill any empty slots in the active pool
            while len(current_active_accounts) < self.config.concurrency:
                # Find an account that is stopped, not currently active
                next_acc_candidate = next((acc for acc in self.accounts if acc.status == 'stopped' and acc not in current_active_accounts), None)
                if not next_acc_candidate:
                    break # No available accounts to start
                
                next_acc = next_acc_candidate

                # Pre-start check: skip if account is already known to be logged out
                if self.state_manager.is_account_logged_out(next_acc.name):
                    print(f"[{next_acc.name}] is marked as logged out. Skipping and moving to end of queue.")
                    # Move to end of queue to prevent it from being checked again immediately
                    self.accounts.remove(next_acc)
                    self.accounts.append(next_acc)
                    continue

                print(f"Trying to start {next_acc.name} to fill active pool slot.")
                if next_acc.start():
                    # Wait a bit between account starts to avoid window conflicts
                    time.sleep(2)
                    if next_acc.find_window():
                        with self.gui_lock:
                            try:
                                # Use the new, dedicated startup screen check.
                                if next_acc.driver.wait_for_startup_screen(timeout=60):
                                    next_acc.status = "idle"
                                    next_acc.ads_sent_in_current_round.clear() # Reset round state
                                    next_acc.round_start_time = datetime.datetime.now()
                                    current_active_accounts.append(next_acc)
                                    print(f"[{next_acc.name}] Added to active pool and ready for tasks.")
                                else:
                                    print(f"[{next_acc.name}] App failed to initialize (startup screen not found). Stopping.")
                                    next_acc.stop()
                            except AccountLoggedOutException:
                                print(f"[{next_acc.name}] Detected as logged out during startup. Marking and stopping.")
                                self.state_manager.mark_account_as_logged_out(next_acc.name)
                                next_acc.stop()
                    else:
                        print(f"[{next_acc.name}] Failed to find window. Stopping.")
                        next_acc.stop()
                else:
                    print(f"[{next_acc.name}] Failed to start process. Stopping.")
                    next_acc.stop()

            tasks_assigned_in_loop = False
            for acc in current_active_accounts:
                if acc.status != "idle":
                    continue

                next_task_info = self._get_next_group_task_for_account(acc)
                
                if next_task_info:
                    tasks_assigned_in_loop = True
                    group_link, cooldown_minutes, group_can_send_links, is_channel, task_type = next_task_info                        
                    entity_type = "channel" if is_channel else "group"
                    print(f"[{acc.name}] Assigned task: {task_type} for '{group_link}' ({entity_type}).")
                    acc.status = "busy"
                    
                    with self.gui_lock: 
                        if acc.activate_window():
                            # Minimize other windows to prevent interference
                            for other_acc in current_active_accounts:
                                if other_acc != acc and other_acc.window and not other_acc.window.isMinimized:
                                    try:
                                        other_acc.window.minimize()
                                    except Exception:
                                        pass
                            
                            success, reason = (False, "FAILURE")
                            try:
                                if task_type == "JOIN":
                                    success, reason = acc.join_group_flow(group_link)
                                    if success:
                                        self.state_manager.update_account_daily_stats(acc.name, "JOIN")
                                        print(f"[{acc.name}] Successfully joined group '{group_link}'.")
                                        time.sleep(random.uniform(2, 5))
                                elif task_type == "JOIN_CHANNEL":
                                    success, reason = acc.join_channel_flow(group_link)
                                    if success:
                                        self.state_manager.update_account_daily_stats(acc.name, "JOIN")
                                        print(f"[{acc.name}] Successfully joined channel '{group_link}'.")
                                        time.sleep(random.uniform(2, 5))
                                elif task_type == "SEND_AD":
                                    success, reason = acc.send_ad_flow(group_link, group_can_send_links)
                                    if success:
                                        self.state_manager.update_group_last_sent_time(acc.name, group_link)
                                        self.state_manager.update_account_daily_stats(acc.name, "SEND_AD")
                                        acc.ads_sent_in_current_round.add(group_link)
                                        print(f"[{acc.name}] Successfully sent ad to '{group_link}'.")
                                
                                if reason == "BANNED":
                                    print(f"[{acc.name}] Task {task_type} for '{group_link}' resulted in a ban. Adding group to this account's ban list.")
                                    self.state_manager.add_banned_group_for_account(acc.name, group_link)
                                elif success:
                                    self.state_manager.reset_failure_count(acc.name, group_link)
                                else:
                                    print(f"[{acc.name}] Task {task_type} for '{group_link}' failed. Incrementing failure count.")
                                    self.state_manager.increment_failure_count(acc.name, group_link)
                            
                            except AccountLoggedOutException:
                                print(f"[{acc.name}] Account detected as logged out during task. Marking and stopping.")
                                self.state_manager.mark_account_as_logged_out(acc.name)
                                acc.stop()
                                # Break out of task loop for this account
                                break
                            
                        else: 
                            print(f"[{acc.name}] Failed to activate window. Task skipped.")
                            self.state_manager.increment_failure_count(acc.name, group_link)
                        
                        acc.status = "idle" # Set back to idle to pick up the next task
                else:
                    # No more tasks available for this account in this round.
                    print(f"[{acc.name}] No more tasks available in this round. Stopping account for rotation.")
                    acc.stop() # This will mark it for removal in the next iteration.

            # If no tasks were assigned and there are active accounts, it means we are waiting for cooldowns.
            if not tasks_assigned_in_loop and current_active_accounts:
                wait_time = 60
                print(f"\nAll available tasks are on cooldown. Entering standby mode for {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                time.sleep(1) # Standard 1-second delay between loop iterations

        print("Bot Controller finished.")
