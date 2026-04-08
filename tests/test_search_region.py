import os
import sys
import time
import pyautogui
import webbrowser

# This utility script helps determine the bounding box of the search results area.
# It works by finding all occurrences of the search result images and calculating
# a box that contains all of them.

def find_search_result_region(account_name: str):
    """
    Finds all search result icons and calculates a bounding box for them.
    """
    print("--- Search Result Region Finder ---")
    print("Please follow these steps:")
    print("1. Manually open and position the Telegram window for the account you want to test.")
    print(f"   (Ensure it's the window for '{account_name}')")
    print("2. In Telegram, click the search bar and type a generic letter like 'a' to bring up a list of results.")
    print("3. Make sure several search results are visible on the screen.")
    input("4. Press Enter in this terminal when you are ready to proceed...")

    print("\nScanning the screen for 'search_result_black.png' and 'search_result_blue.png'...")

    image_paths = [
        os.path.join("data", "images", "search_result_black.png"),
        os.path.join("data", "images", "search_result_blue.png")
    ]

    all_found_boxes = []
    for path in image_paths:
        if not os.path.exists(path):
            print(f"Warning: Image not found at {path}")
            continue
        try:
            found_boxes = list(pyautogui.locateAllOnScreen(path, confidence=0.8))
            if found_boxes:
                print(f"Found {len(found_boxes)} instance(s) of '{os.path.basename(path)}'.")
                all_found_boxes.extend(found_boxes)
            else:
                print(f"Found 0 instances of '{os.path.basename(path)}'.")
        except pyautogui.ImageNotFoundException:
            pass # This is expected if one of the images isn't on screen
        except Exception as e:
            print(f"An error occurred during image search: {e}")

    if not all_found_boxes:
        print("\n--- ERROR ---")
        print("Could not find any search result icons on the screen.")
        print("Please ensure the Telegram window is visible and shows a list of search results.")
        return

    # Calculate the bounding box that contains all found icons
    min_x = min(box.left for box in all_found_boxes)
    min_y = min(box.top for box in all_found_boxes)
    max_x = max(box.left + box.width for box in all_found_boxes)
    max_y = max(box.top + box.height for box in all_found_boxes)

    # Add some padding to the region to be safe
    padding = 20
    region_left = min_x - padding
    region_top = min_y - padding
    region_width = (max_x - min_x) + (2 * padding)
    region_height = (max_y - min_y) + (2 * padding)

    calculated_region = (region_left, region_top, region_width, region_height)

    print("\n--- RESULTS ---")
    print(f"Found a total of {len(all_found_boxes)} search result items.")
    print(f"Calculated optimal search region (with {padding}px padding):")
    print(f"SEARCH_RESULT_REGION = {calculated_region}")

    # Create a screenshot and draw the rectangle to provide visual feedback
    screenshot_path = os.path.join("results", "debug_screenshots", "search_region_test.png")
    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
    
    # Use a library that can draw on images, or just take a screenshot and open it
    # For simplicity, we'll just save the screenshot and print the path.
    # A more advanced script would use Pillow to draw the rectangle.
    pyautogui.screenshot(screenshot_path)
    
    print(f"\nA full screenshot has been saved to: {screenshot_path}")
    print("Please open it to see what the script saw. You can manually draw a rectangle")
    print("using the coordinates above in an image editor to verify the calculated region.")
    
    # Open the image for the user
    try:
        webbrowser.open(os.path.abspath(screenshot_path))
    except Exception:
        print("Could not automatically open the screenshot.")


if __name__ == "__main__":
    # Default account to test if none is provided via command line
    DEFAULT_ACCOUNT = "Telegram 001"
    account_to_run = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ACCOUNT
    find_search_result_region(account_to_run)
