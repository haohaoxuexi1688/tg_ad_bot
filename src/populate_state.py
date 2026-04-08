import json
import os

STATE_FILE_PATH = os.path.join("results", "state.json")
TEMPLATE_ACCOUNT = "Telegram 001"

def populate_joined_groups():
    """
    Populates the 'joined_groups' field for all other accounts (002-030)
    based on the list from the template account (001).
    """
    print(f"Attempting to read state file from: {STATE_FILE_PATH}")
    
    if not os.path.exists(STATE_FILE_PATH):
        print(f"Error: State file not found at '{STATE_FILE_PATH}'. Please run the main bot once to generate it.")
        return

    try:
        with open(STATE_FILE_PATH, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
        print("Successfully loaded state file.")
    except Exception as e:
        print(f"Error reading or parsing JSON from state file: {e}")
        return

    # Ensure the 'joined_groups' key and the template account exist
    if 'joined_groups' not in state_data:
        state_data['joined_groups'] = {}
        
    if TEMPLATE_ACCOUNT not in state_data['joined_groups']:
        print(f"Error: Template account '{TEMPLATE_ACCOUNT}' not found in 'joined_groups'.")
        print("Please ensure this account has joined at least one group.")
        return
        
    # Get the template list of groups
    template_groups = state_data['joined_groups'][TEMPLATE_ACCOUNT]
    print(f"Using group list from '{TEMPLATE_ACCOUNT}': {len(template_groups)} groups.")

    # Loop through accounts 002 to 030 and apply the template
    updated_count = 0
    for i in range(2, 31):
        account_name = f"Telegram {i:03d}"
        
        # Avoid overwriting if it already exists and is identical, but for this task, we just overwrite.
        state_data['joined_groups'][account_name] = template_groups
        updated_count += 1
        
    print(f"Populated 'joined_groups' for {updated_count} accounts (002-030).")

    # Write the modified data back to the file
    try:
        with open(STATE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state_data, f, indent=4)
        print(f"Successfully saved updated state to '{STATE_FILE_PATH}'.")
    except Exception as e:
        print(f"Error writing updated state to file: {e}")

if __name__ == "__main__":
    populate_joined_groups()
