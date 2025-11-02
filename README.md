# FBi Radio to RSS

A Python script to scrape FBi Radio programme pages and generate podcast RSS feeds for each show.

## Features

- Scrapes episode information from FBi Radio programme pages
- Extracts episode titles, dates, descriptions, and audio URLs
- Generates RSS feeds in podcast format
- Supports multiple shows (configurable)
- Episodes sorted in reverse chronological order (newest first)
- Direct audio file URLs for podcast compatibility

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

Run the script to generate RSS feeds for all configured programmes:

```bash
uv run python fbi_to_rss.py
```

This will:
- Scrape episode data from each configured programme
- Generate RSS feed XML files (e.g., `jack_off_feed.xml`, `loose_joints_feed.xml`, `wildcard_with_stuart_coupe_feed.xml`)

### Supported Programmes

The script currently supports these programmes:
- **Jack Off** (`jack-off`)
- **Loose Joints** (`loose-joints`)
- **Wildcard With Stuart Coupe** (`wildcard-with-stuart-coupe`)
- **Sunset with Tangela** (`sunset-with-tangela`)
- **Utility Fog** (`utility-fog`)

### Adding New Programmes

To add a new programme, you need to:

1. **Edit the `main()` function** in `fbi_to_rss.py` to add the programme:
   ```python
   programs = [
       ('jack-off', 'Jack Off'),
       ('loose-joints', 'Loose Joints'),
       ('wildcard-with-stuart-coupe', 'Wildcard With Stuart Coupe'),
       ('sunset-with-tangela', 'Sunset with Tangela'),
       ('utility-fog', 'Utility Fog'),
       ('new-programme-slug', 'New Programme Name'),
   ]
   ```

2. **Find and add the show UUID** in the `KNOWN_SHOW_IDS` dictionary at the top of the `FBIRadioScraper` class:
   ```python
   KNOWN_SHOW_IDS = {
       'jack-off': '85ea9d91-cb57-46c4-a9c6-abe601048b69',
       'loose-joints': 'e8d27dbf-88c7-4901-9560-b37b0064b8ec',
       'wildcard-with-stuart-coupe': 'cec7fc63-681b-4126-a98c-b37d00232daa',
       'sunset-with-tangela': '018aa123-6990-463e-8983-b37f0095b36a',
       'utility-fog': '1e142c09-9e63-4d2e-8ce7-a00df26cf834',
       'new-program-slug': 'show-uuid-here',
   }
   ```

   The show UUID is specific to each programme and is required to construct the correct Omny Studio audio URLs. You can find it by:
   - Checking the programme's Omny Studio configuration on the programme page
   - Inspecting a working episode's audio URL structure
   - Comparing UUIDs found on the programme page vs. episode pages (the show ID appears on the programme page but not on individual episode pages)
   - Or letting the script attempt to discover it automatically (may not always work)

**Note**: Simply adding a programme name without the show UUID will likely result in incorrect or missing audio URLs in the RSS feed.

## Output

The script generates RSS feed XML files in the current directory:
- `jack_off_feed.xml` - RSS feed for Jack Off
- `loose_joints_feed.xml` - RSS feed for Loose Joints
- `wildcard_with_stuart_coupe_feed.xml` - RSS feed for Wildcard With Stuart Coupe
- `sunset_with_tangela_feed.xml` - RSS feed for Sunset with Tangela
- `utility_fog_feed.xml` - RSS feed for Utility Fog

Each RSS feed includes:
- Programme title and description
- All episodes with titles, dates, descriptions
- Audio URLs (when available)
- Episodes sorted newest first

## How It Works

1. **Scraping**: The script fetches the programme page HTML and extracts embedded JSON data (Nuxt.js stores data in `window.__NUXT__`)
2. **Episode Discovery**: Episodes are extracted from the JSON data structure or HTML links as fallback
3. **Audio URLs**: The script constructs Omny Studio audio URLs using the format:
   - `https://traffic.omny.fm/d/clips/{orgId}/{showId}/{clipId}/audio.mp3`
   - The `orgId` is extracted from FBi Radio's configuration
   - The `showId` is programme-specific and stored in `KNOWN_SHOW_IDS`
   - The `clipId` is episode-specific and extracted from each episode page
4. **RSS Generation**: Uses `feedgen` library to create standard podcast RSS feeds, with episodes sorted in reverse chronological order (newest first)
5. **Order Preservation**: After feedgen generates the RSS, the script manually reorders items to ensure newest episodes appear first, as feedgen may reorder entries automatically

## Notes

- The script respects rate limits by using a session with proper headers
- Audio URLs may not always be available depending on FBi Radio's setup
- The script handles both JSON-embedded data and HTML fallback parsing
- Each episode requires fetching the episode page to extract the clip UUID for audio URLs
- Episodes are sorted in reverse chronological order (newest first) in the RSS feeds

## Licence

GPL 3.0 Licence - see LICENSE file for details.

