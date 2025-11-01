# FBi Radio to RSS

A Python script to scrape FBi Radio program pages and generate podcast RSS feeds for each show.

## Features

- Scrapes episode information from FBi Radio program pages
- Extracts episode titles, dates, descriptions, and audio URLs
- Generates RSS feeds in podcast format
- Supports multiple shows (configurable)
- Episodes sorted in reverse chronological order (newest first)

## Requirements

- Python 3.9+
- `uv` for package management

## Installation

1. Install `uv` if you haven't already:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

## Usage

Run the script to generate RSS feeds for all configured programs:

```bash
uv run python fbi_to_rss.py
```

This will:
- Scrape episode data from each configured program
- Generate RSS feed XML files (e.g., `jack_off_feed.xml`, `loose_joints_feed.xml`)

### Customizing Programs

Edit the `main()` function in `fbi_to_rss.py` to add or modify programs:

```python
programs = [
    ('jack-off', 'Jack Off'),
    ('loose-joints', 'Loose Joints'),
    # Add more programs here
]
```

## Output

The script generates RSS feed XML files in the current directory:
- `jack_off_feed.xml` - RSS feed for Jack Off
- `loose_joints_feed.xml` - RSS feed for Loose Joints

Each RSS feed includes:
- Program title and description
- All episodes with titles, dates, descriptions
- Audio URLs (when available)
- Episodes sorted newest first

## How It Works

1. **Scraping**: The script fetches the program page HTML and extracts embedded JSON data (Nuxt.js stores data in `window.__NUXT__`)
2. **Episode Discovery**: Episodes are extracted from the JSON data structure or HTML links as fallback
3. **Audio URLs**: The script attempts to find audio URLs from Omny Studio (FBi Radio's audio hosting platform)
4. **RSS Generation**: Uses `feedgen` library to create standard podcast RSS feeds

## Notes

- The script respects rate limits by using a session with proper headers
- Audio URLs may not always be available depending on FBi Radio's setup
- The script handles both JSON-embedded data and HTML fallback parsing

## License

MIT License - feel free to use and modify as needed.

