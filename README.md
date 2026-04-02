# Google Photos Bulk Deleter

Automates the deletion of all photos from your Google Photos library using browser automation.

Google Photos has no built-in "delete all" option and the API doesn't support deleting photos from your library. This tool uses [Playwright](https://playwright.dev/python/) to drive your real Chrome browser, selecting and deleting photos in batches.

## How It Works

1. Launches Chrome using your existing profile (so you're already logged in)
2. Navigates to [photos.google.com](https://photos.google.com)
3. Selects photos in configurable batches (default: 50)
4. Moves them to Trash via the Google Photos UI
5. Repeats until no photos remain

Photos are moved to Trash first and can be recovered for 60 days. Use `--empty-trash` to permanently delete them immediately.

## Requirements

- Python 3.9+
- Google Chrome installed
- A Google account with photos to delete

## Installation

```bash
git clone https://github.com/pfussell/PhotoDelete.git
cd PhotoDelete
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Usage

### Dry run (test without deleting anything)

```bash
python delete_google_photos.py --dry-run
```

### Delete all photos

```bash
python delete_google_photos.py
```

You will be prompted to type `DELETE` to confirm.

### Options

| Flag | Description |
|------|-------------|
| `--batch-size N` | Photos to select per batch (default: 50, max: 500) |
| `--dry-run` | Select one batch but don't delete (test mode) |
| `--empty-trash` | Permanently delete by emptying Trash after moving photos |

### Examples

```bash
# Delete in larger batches
python delete_google_photos.py --batch-size 200

# Delete everything permanently
python delete_google_photos.py --batch-size 200 --empty-trash
```

## How Login Works

The script copies your existing Chrome profile to a temporary directory so it can reuse your Google login session without interfering with your running Chrome. If you're not logged in, it will open the Google sign-in page and wait for you to log in manually.

## Stopping

Press `Ctrl+C` at any time to stop. The script will print how many photos were deleted in the current session.

## Limitations

- Google Photos may rate-limit or show CAPTCHAs after many deletions. If the script stalls, stop and retry later.
- The script relies on Google Photos' current DOM structure. If Google updates their UI, selectors may need updating.
- Only works with Google Chrome (not Firefox or Safari).

## Platform Support

| Platform | Status |
|----------|--------|
| macOS | Tested |
| Linux | Supported |
| Windows | Supported |

## License

MIT
