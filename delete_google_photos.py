#!/usr/bin/env python3
"""
Google Photos Bulk Deleter

Automates the deletion of all photos from Google Photos using browser automation.
You will log in manually, then the script selects and deletes photos in batches.

Usage:
    python delete_google_photos.py [--batch-size 50] [--dry-run]
"""

import argparse
import glob
import os
import platform
import shutil
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


GOOGLE_PHOTOS_URL = "https://photos.google.com"
DEFAULT_BATCH_SIZE = 100
# Max photos Google lets you select/delete at once
MAX_BATCH_SIZE = 500


def find_chrome_path():
    """Find the real Chrome installation on this system."""
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser(
                "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            ),
        ]
    elif system == "Linux":
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
    else:  # Windows
        candidates = [
            os.path.expandvars(
                r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"
            ),
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
            ),
            os.path.expandvars(
                r"%LocalAppData%\Google\Chrome\Application\chrome.exe"
            ),
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def get_chrome_user_data_dir():
    """Get the default Chrome user data directory."""
    system = platform.system()
    if system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/Google/Chrome")
    elif system == "Linux":
        return os.path.expanduser("~/.config/google-chrome")
    else:
        return os.path.expandvars(r"%LocalAppData%\Google\Chrome\User Data")


def wait_for_login(page):
    """Wait for the user to log in to Google."""
    print("\n=== Manual Login Required ===")
    print("A browser window has opened. Please log in to your Google account.")
    print("Once you have finished logging in, press ENTER here to continue...")
    input()
    print("Login complete.\n")


def scroll_to_load_photos(page, target_count):
    """Scroll down to load enough photo thumbnails."""
    for _ in range(10):
        loaded = page.query_selector_all('div[role="checkbox"][aria-label]')
        if len(loaded) >= target_count:
            break
        page.keyboard.press("End")
        time.sleep(1)


def get_photo_checkboxes(page):
    """Return all photo checkbox elements using the actual Google Photos DOM."""
    # From the error log: checkboxes are div[role="checkbox"] with aria-label starting with "Photo" or "Video"
    selectors = [
        'div[role="checkbox"][aria-label^="Photo"]',
        'div[role="checkbox"][aria-label^="Video"]',
        'div[role="checkbox"][class*="ckGgle"]',
        'div[role="checkbox"][aria-label]',
    ]
    for selector in selectors:
        elements = page.query_selector_all(selector)
        if elements:
            return elements, selector
    return [], None


def select_all_photos_in_view(page, batch_size):
    """
    Select photos by clicking each checkbox individually via JavaScript.
    Returns the number of photos selected.
    """
    checkboxes, selector = get_photo_checkboxes(page)
    if not checkboxes:
        return 0

    count_to_select = min(len(checkboxes), batch_size)
    if count_to_select == 0:
        return 0

    # Click all checkboxes in one JavaScript call for speed
    selected = page.evaluate("""(args) => {
        const [selector, count] = args;
        const boxes = document.querySelectorAll(selector);
        let clicked = 0;
        for (let i = 0; i < Math.min(boxes.length, count); i++) {
            boxes[i].dispatchEvent(new MouseEvent('click', {bubbles: true}));
            clicked++;
        }
        return clicked;
    }""", [selector, count_to_select])

    time.sleep(1)
    return selected


def get_selected_count(page):
    """Try to read the selection count from the top bar."""
    # Google Photos shows "X selected" or "X items selected" in the toolbar
    selectors = [
        'span:has-text("selected")',
        'div[aria-label*="selected"]',
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text()
                # Extract number from text like "50 selected"
                parts = text.split()
                for part in parts:
                    if part.isdigit():
                        return int(part)
        except Exception:
            pass
    return None


def js_click(element):
    """Click an element via JavaScript to bypass overlay interception."""
    element.dispatch_event("click")


def delete_selected(page):
    """Click the delete/trash button and confirm the deletion."""
    # Look for the trash/delete button in the toolbar
    delete_selectors = [
        'button[aria-label="Delete"]',
        'button[aria-label="Move to trash"]',
        'button[aria-label="Move to Trash"]',
        '[aria-label="Delete"]',
        '[aria-label="Move to trash"]',
    ]

    delete_btn = None
    for sel in delete_selectors:
        delete_btn = page.query_selector(sel)
        if delete_btn:
            break

    if not delete_btn:
        # Try pressing the delete key as a shortcut
        print("  Could not find delete button, trying keyboard shortcut (#)...")
        page.keyboard.press("#")
        time.sleep(1)
    else:
        js_click(delete_btn)
        time.sleep(1)

    # Confirm the deletion in the dialog
    confirm_selectors = [
        'button:has-text("Move to trash")',
        'button:has-text("Move to Trash")',
        'button:has-text("Delete")',
        'button:has-text("Allow")',
        'button:has-text("Move")',
    ]

    for sel in confirm_selectors:
        try:
            confirm_btn = page.query_selector(sel)
            if confirm_btn:
                js_click(confirm_btn)
                time.sleep(2)
                return True
        except Exception:
            continue

    print("  Warning: Could not find confirmation button. Check the browser.")
    return False


def empty_trash(page):
    """Navigate to trash and empty it permanently."""
    print("\n=== Emptying Trash ===")
    page.goto("https://photos.google.com/trash")
    time.sleep(3)

    empty_btn = page.query_selector(
        'button:has-text("Empty trash"), '
        'button:has-text("Empty Trash")'
    )
    if empty_btn:
        js_click(empty_btn)
        time.sleep(1)
        # Confirm
        confirm = page.query_selector(
            'button:has-text("Empty trash"), '
            'button:has-text("Delete"), '
            'button:has-text("Empty Trash")'
        )
        if confirm and confirm != empty_btn:
            js_click(confirm)
            time.sleep(3)
        print("Trash emptied.")
    else:
        print("No 'Empty trash' button found (trash may already be empty).")


def run(batch_size=DEFAULT_BATCH_SIZE, dry_run=False, headless=False, empty_trash_after=False):
    """Main loop: select batches of photos and delete them."""
    chrome_path = find_chrome_path()
    if not chrome_path:
        print("ERROR: Could not find Google Chrome. Please install it first.")
        sys.exit(1)

    print(f"Using Chrome at: {chrome_path}")

    # Copy Chrome profile to a temp dir so we don't conflict with a running Chrome
    chrome_user_data = get_chrome_user_data_dir()
    temp_profile = tempfile.mkdtemp(prefix="photo_delete_profile_")

    if os.path.exists(chrome_user_data):
        print("Copying Chrome profile (this may take a moment)...")
        # Only copy the Default profile and key files to keep it fast
        for item in ["Default", "Local State"]:
            src = os.path.join(chrome_user_data, item)
            dst = os.path.join(temp_profile, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                    "Cache", "Code Cache", "GPUCache", "Service Worker",
                    "CacheStorage", "blob_storage", "*.log",
                ))
            elif os.path.isfile(src):
                shutil.copy2(src, dst)
        print("Profile copied.\n")
    else:
        print("No existing Chrome profile found. You'll need to log in.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=temp_profile,
            executable_path=chrome_path,
            headless=headless,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1920, "height": 1080},
            no_viewport=True,
        )
        page = browser.new_page()

        # Navigate to Google Photos
        page.goto(GOOGLE_PHOTOS_URL)
        time.sleep(3)

        # Check if we got redirected away (not logged in)
        current = page.url
        if "photos.google.com" not in current or "/about" in current:
            print("Not logged in — redirected to: " + current)
            page.goto("https://accounts.google.com/signin")
            time.sleep(2)
            wait_for_login(page)

        # Always navigate explicitly to Google Photos after login
        print("Navigating to Google Photos...")
        page.goto(GOOGLE_PHOTOS_URL)
        time.sleep(3)

        # If still redirected, retry once more
        current = page.url
        if "photos.google.com" not in current or "/about" in current:
            print(f"Landed on {current} — retrying navigation...")
            page.goto(GOOGLE_PHOTOS_URL)
            time.sleep(3)

        current = page.url
        if "photos.google.com" not in current or "/about" in current:
            print(f"\nStill not on Google Photos (at {current}).")
            print("Please navigate to https://photos.google.com in the browser,")
            print("then press ENTER here once you see your photo library...")
            input()

        print("On Google Photos library.\n")

        total_deleted = 0
        consecutive_failures = 0
        max_failures = 5

        print(f"Starting deletion (batch size: {batch_size}, dry run: {dry_run})")
        print("Press Ctrl+C at any time to stop.\n")

        try:
            while True:
                # Make sure we're on the main photos page
                if "photos.google.com" not in page.url or "trash" in page.url or "/about" in page.url:
                    page.goto(GOOGLE_PHOTOS_URL)
                    time.sleep(3)

                # Scroll to ensure photos are loaded
                scroll_to_load_photos(page, batch_size)
                time.sleep(1)

                # Check if there are any photos left
                photos, _ = get_photo_checkboxes(page)
                if not photos:
                    print("\nNo more photos found. Done!")
                    break

                print(f"Batch: selecting up to {batch_size} photos "
                      f"(~{len(photos)} visible)...")

                selected = select_all_photos_in_view(page, batch_size)
                if selected == 0:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        print(f"\nFailed to select photos {max_failures} times in a row. "
                              "Stopping.")
                        break
                    print("  No photos selected, retrying...")
                    page.goto(GOOGLE_PHOTOS_URL)
                    time.sleep(3)
                    continue

                # Read actual selection count if available
                actual = get_selected_count(page)
                count_str = f"{actual}" if actual else f"~{selected}"
                print(f"  Selected {count_str} photos.")

                if dry_run:
                    print("  [DRY RUN] Would delete these photos. Pressing Escape.")
                    page.keyboard.press("Escape")
                    time.sleep(1)
                    total_deleted += selected
                    consecutive_failures = 0
                    break  # In dry run, just do one batch
                else:
                    success = delete_selected(page)
                    if success:
                        deleted_count = actual if actual else selected
                        total_deleted += deleted_count
                        consecutive_failures = 0
                        print(f"  Deleted. Total so far: {total_deleted}")
                    else:
                        consecutive_failures += 1
                        if consecutive_failures >= max_failures:
                            print(f"\nFailed to delete {max_failures} times. Stopping.")
                            break
                        print("  Delete may have failed, retrying...")
                        page.keyboard.press("Escape")

                # Brief pause between batches
                time.sleep(2)

        except KeyboardInterrupt:
            print(f"\n\nStopped by user. Total deleted: {total_deleted}")

        if empty_trash_after and not dry_run and total_deleted > 0:
            empty_trash(page)

        print(f"\n{'=' * 40}")
        print(f"Total photos {'selected (dry run)' if dry_run else 'deleted'}: "
              f"{total_deleted}")
        if not dry_run and total_deleted > 0 and not empty_trash_after:
            print("\nNote: Photos were moved to Trash. They will be permanently")
            print("deleted after 60 days, or you can run with --empty-trash to")
            print("empty the trash immediately.")
        print(f"{'=' * 40}")

        input("\nPress ENTER to close the browser...")
        browser.close()

        # Clean up temp profile
        try:
            shutil.rmtree(temp_profile, ignore_errors=True)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="Bulk delete all photos from Google Photos"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Photos to delete per batch (default: {DEFAULT_BATCH_SIZE}, "
             f"max: {MAX_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Select one batch but don't actually delete (test mode)",
    )
    parser.add_argument(
        "--empty-trash",
        action="store_true",
        help="Empty the trash after deletion to permanently remove photos",
    )
    args = parser.parse_args()

    batch_size = min(args.batch_size, MAX_BATCH_SIZE)

    print("=" * 50)
    print("  Google Photos Bulk Deleter")
    print("=" * 50)
    if args.dry_run:
        print("  MODE: Dry Run (no photos will be deleted)")
    else:
        print("  WARNING: This will DELETE your Google Photos!")
        print("  Photos go to Trash first (recoverable for 60 days).")
    print(f"  Batch size: {batch_size}")
    print("=" * 50)

    if not args.dry_run:
        confirm = input("\nType 'DELETE' to confirm: ")
        if confirm != "DELETE":
            print("Aborted.")
            sys.exit(0)

    run(
        batch_size=batch_size,
        dry_run=args.dry_run,
        empty_trash_after=args.empty_trash,
    )


if __name__ == "__main__":
    main()
