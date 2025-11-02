#!/usr/bin/env python3
"""
FBi Radio to RSS Podcast Feed Generator

Scrapes episode information from FBi radio program pages and generates
podcast RSS feeds for each show.
"""

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
import re
import json
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
import sys


class FBIRadioScraper:
    """Scraper for FBi Radio program pages."""
    
    BASE_URL = "https://www.fbi.radio"
    OMNYY_STUDIO_BASE = "https://omny.fm/shows"
    
    # Known show IDs per program (extracted from working URLs)
    # These can be updated as needed when we discover them
    KNOWN_SHOW_IDS = {
        'jack-off': '85ea9d91-cb57-46c4-a9c6-abe601048b69',
        'loose-joints': 'e8d27dbf-88c7-4901-9560-b37b0064b8ec',
        'wildcard-with-stuart-coupe': 'cec7fc63-681b-4126-a98c-b37d00232daa',
        'sunset-with-tangela': '018aa123-6990-463e-8983-b37f0095b36a',
        'utility-fog': '1e142c09-9e63-4d2e-8ce7-a00df26cf834',
    }
    
    # Known programme image URLs (for programmes where auto-extraction doesn't work reliably)
    KNOWN_PROGRAMME_IMAGES = {
        'sunset-with-tangela': 'https://media.fbi.radio/images/sunset%20with%20tangela-800x450.jpg',
        'utility-fog': 'https://media.fbi.radio/images/utility%20fog%20with%20peter%20hollo-800x450.jpg',
    }
    
    def __init__(self, program_slug: str):
        """
        Initialize scraper for a specific program.
        
        Args:
            program_slug: URL slug for the program (e.g., 'jack-off', 'loose-joints')
        """
        self.program_slug = program_slug
        self.program_url = f"{self.BASE_URL}/programs/{program_slug}"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.show_id = None  # Cache for show ID (program-specific)
    
    def fetch_page(self, url: str) -> Optional[str]:
        """Fetch a webpage and return raw HTML."""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)
            return None
    
    def extract_json_data(self, html: str) -> Optional[Dict]:
        """Extract JSON data from Nuxt.js script tags."""
        # Look for window.__NUXT__ data - it can be a full object or just {}
        # Pattern: window.__NUXT__ = {...}; or window.__NUXT__={...};
        patterns = [
            r'window\.__NUXT__\s*=\s*({.+?});',
            r'window\.__NUXT__\s*=\s*({[^}]*data[^}]*\[[^\]]*\]);',
            r'window\.__NUXT__\s*=\s*({[^}]*\.data[^}]*});',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    json_str = match.group(1)
                    # Try to parse as JSON
                    data = json.loads(json_str)
                    if isinstance(data, dict) and len(data) > 0:
                        return data
                except json.JSONDecodeError:
                    # Try to extract just the data portion if it exists
                    try:
                        # Look for data: [...] pattern
                        data_match = re.search(r'"data"\s*:\s*(\[[^\]]+\])', json_str, re.DOTALL)
                        if data_match:
                            # The actual data might be in a different format
                            # Let's return the whole parsed object anyway
                            if isinstance(data, dict):
                                return data
                    except:
                        pass
        
        # Look for JSON-LD script tags
        soup = BeautifulSoup(html, 'lxml')
        for script in soup.find_all('script', type='application/ld+json'):
            if script.string:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    pass
        
        # Last resort: try to find any JSON-like structure in script tags
        for script in soup.find_all('script'):
            if script.string and 'uuid' in script.string.lower() and '__NUXT__' in script.string:
                # Try to extract JSON from this script
                try:
                    # Look for object-like structures with uuid
                    uuid_match = re.search(r'{"[^"]*uuid[^"]*":[^}]+}', script.string)
                    if uuid_match:
                        # Found something, but parsing might be tricky
                        pass
                except:
                    pass
        
        return None
    
    def extract_episodes_from_json(self, json_data: Dict) -> List[Dict]:
        """Extract episode data from embedded JSON."""
        episodes = []
        
        # Navigate through the JSON structure to find episodes
        # The structure seems to be: __NUXT__.data[0].Episodes.docs
        def find_episodes(data, path=""):
            if isinstance(data, dict):
                # Look for episode-like structures
                if 'airedAt' in data and 'slug' in data and 'title' in data:
                    episode = {
                        'id': data.get('id', ''),
                        'title': data.get('title', 'Untitled'),
                        'slug': data.get('slug', ''),
                        'airedAt': data.get('airedAt', ''),
                        'description': data.get('description', {}).get('root', {}).get('children', []),
                        'omnyStudioClip': data.get('omnyStudioClip', ''),
                    }
                    # Build episode URL
                    if episode['slug']:
                        episode['url'] = f"{self.BASE_URL}/programs/{self.program_slug}/episodes/{episode['slug']}"
                    else:
                        episode['url'] = self.program_url
                    episodes.append(episode)
                    return
                
                # Recursively search
                for key, value in data.items():
                    if key in ['Episodes', 'episodes', 'docs'] or isinstance(value, (dict, list)):
                        find_episodes(value, f"{path}.{key}")
            
            elif isinstance(data, list):
                for item in data:
                    find_episodes(item, path)
        
        find_episodes(json_data)
        return episodes
    
    def extract_episode_links_from_html(self, html: str) -> List[str]:
        """Extract episode links from HTML."""
        soup = BeautifulSoup(html, 'lxml')
        episode_links = []
        
        # Look for links containing '/episodes/'
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if '/episodes/' in href and self.program_slug in href:
                full_url = urljoin(self.BASE_URL, href)
                if full_url not in episode_links:
                    episode_links.append(full_url)
        
        return episode_links
    
    def extract_omny_config(self, html: str) -> Dict[str, str]:
        """Extract Omny Studio configuration from page HTML."""
        config = {}
        # Look for omnyStudio config in the page
        # Format: omnyStudio: { orgId: "..." }
        org_id_match = re.search(r'omnyStudio[^}]*orgId["\']?\s*:\s*["\']([^"\']+)', html, re.I)
        if org_id_match:
            config['orgId'] = org_id_match.group(1)
        return config
    
    def find_uuid_in_data(self, data, target_ref=None):
        """Recursively find UUID in JSON data structure."""
        if isinstance(data, dict):
            # Check if this is a Clip with uuid
            typename = str(data.get('__typename', ''))
            if 'uuid' in data:
                uuid = data.get('uuid', '')
                # Valid UUID format check (has dashes and is long enough)
                if uuid and '-' in uuid and len(uuid) > 30:
                    # If we have a target ref, check if this matches
                    if target_ref:
                        ref = data.get('__ref', '')
                        if target_ref in str(ref) or str(ref) in str(target_ref):
                            return uuid
                    # If no target, just return first valid UUID we find
                    elif not target_ref:
                        return uuid
            
            # Recursively search
            for key, value in data.items():
                # Skip very large arrays
                if isinstance(value, list) and len(value) > 1000:
                    continue
                result = self.find_uuid_in_data(value, target_ref)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self.find_uuid_in_data(item, target_ref)
                if result:
                    return result
        return None
    
    def extract_audio_url_from_episode_page(self, html: str) -> Optional[str]:
        """Extract Omny Studio audio URL from episode page HTML.
        
        URL format: https://traffic.omny.fm/d/clips/{orgId}/{showId}/{clipId}/audio.mp3
        """
        # Extract org ID first (we'll need it later)
        org_id = None
        org_id_match = re.search(r'omnyStudio[^}]*orgId["\']?\s*:\s*["\']([^"\']+)', html, re.I)
        if org_id_match:
            org_id = org_id_match.group(1)
        
        if not org_id:
            org_id = "02b00798-16d7-4067-89ac-aba000ffd8cb"  # Default from FBi Radio
        
        # First, try to find the complete URL pattern directly in the HTML
        # This is the most reliable method
        audio_url_patterns = [
            r'https://traffic\.omny\.fm/d/clips/[a-f0-9\-]+/[a-f0-9\-]+/[a-f0-9\-]+/audio\.mp3',
            r'https://traffic\.omny\.fm/d/clips/[^"\'\s\)]+/audio\.mp3',
            r'traffic\.omny\.fm/d/clips/[a-f0-9\-]+/[a-f0-9\-]+/[a-f0-9\-]+/audio\.mp3',
            r'traffic\.omny\.fm/d/clips/[^"\'\s\)]+/audio\.mp3',
        ]
        
        for pattern in audio_url_patterns:
            match = re.search(pattern, html, re.I)
            if match:
                url = match.group(0)
                if not url.startswith('http'):
                    url = 'https://' + url
                return url
        
        # Also try searching for UUIDs directly in HTML using regex
        # UUIDs are 36 chars: 8-4-4-4-12 hex digits with dashes
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        uuids_in_html = re.findall(uuid_pattern, html, re.I)
        unique_uuids = list(dict.fromkeys(uuids_in_html))  # Preserve order, remove dupes
        
        # Filter out the org_id and build ID (buildId is in the Nuxt config)
        build_id_match = re.search(r'buildId["\']?\s*:\s*["\']([^"\']+)', html, re.I)
        build_id = build_id_match.group(1) if build_id_match else None
        
        unique_uuids = [u for u in unique_uuids if u.lower() != org_id.lower()]
        if build_id:
            unique_uuids = [u for u in unique_uuids if u.lower() != build_id.lower()]
        
        # The show ID might not be on the episode page - try to get it from known values, omnyStudioClip, or program page
        show_uuid_direct = None
        if hasattr(self, 'show_id') and self.show_id:
            show_uuid_direct = self.show_id
        elif self.program_slug in self.KNOWN_SHOW_IDS:
            # Use known show ID for this program
            show_uuid_direct = self.KNOWN_SHOW_IDS[self.program_slug]
            self.show_id = show_uuid_direct
        else:
            # First try to extract from omnyStudioClip in the JSON
            json_data = self.extract_json_data(html)
            if json_data:
                # Look for omnyStudioClip references in JSON
                omny_clip_ref = self._find_omny_clip_reference(json_data)
                if omny_clip_ref and 'showId' in str(omny_clip_ref):
                    # Try to extract show ID from the clip reference
                    show_id_match = re.search(r'"showId"\s*:\s*"([^"]+)"', str(omny_clip_ref), re.I)
                    if show_id_match:
                        show_uuid_direct = show_id_match.group(1)
                        self.show_id = show_uuid_direct
            
            # If not found, try to extract show ID from program page
            if not show_uuid_direct:
                program_html = self.fetch_page(self.program_url)
                if program_html:
                    # Look for omnyStudio configuration on program page
                    omny_config_match = re.search(r'omnyStudio[^}]*showId["\']?\s*:\s*["\']([^"\']+)', program_html, re.I)
                    if omny_config_match:
                        show_uuid_direct = omny_config_match.group(1)
                        self.show_id = show_uuid_direct
                    else:
                        # Try extracting UUIDs from program page
                        program_uuids = re.findall(uuid_pattern, program_html, re.I)
                        program_unique = [u for u in list(dict.fromkeys(program_uuids)) if u.lower() != org_id.lower()]
                        # The show ID is often one that's NOT on the episode page
                        for uuid in program_unique:
                            if uuid not in unique_uuids and uuid != org_id:  # Show ID shouldn't be in episode page
                                show_uuid_direct = uuid
                                self.show_id = uuid  # Cache it
                                break
        
        if len(unique_uuids) >= 1:
            # The clip ID is the episode-specific UUID, usually the one associated with the title
            # Based on the example, it's: 0b239285-ff32-4160-aad8-b38800644870
            # This is usually one of the UUIDs on the episode page
            # Prefer UUIDs that appear earlier in the page (episode-specific ones usually come first)
            # Skip the build ID which we already filtered out
            # Use the first UUID that's not the show ID as the clip ID
            clip_uuid_direct = None
            for uuid in unique_uuids:
                if uuid != show_uuid_direct:
                    clip_uuid_direct = uuid
                    break
            # Fallback to last UUID if we didn't find a different one
            if not clip_uuid_direct:
                clip_uuid_direct = unique_uuids[-1]
            
            # If we found show ID from program page, use it
            if show_uuid_direct:
                direct_url = f"https://traffic.omny.fm/d/clips/{org_id}/{show_uuid_direct}/{clip_uuid_direct}/audio.mp3"
                return direct_url
            elif len(unique_uuids) >= 2:
                # Fallback: use first UUID as show, last as clip
                show_uuid_direct = unique_uuids[0]
                direct_url = f"https://traffic.omny.fm/d/clips/{org_id}/{show_uuid_direct}/{clip_uuid_direct}/audio.mp3"
                return direct_url
        
        # If not found via direct UUID search, try extracting from JSON data
        
        # Extract JSON data to find UUIDs
        json_data = self.extract_json_data(html)
        if not json_data:
            return None
        
        # Find all UUIDs in the JSON structure, tracking their context
        uuid_to_info = {}  # uuid -> {'type': 'clip'|'show'|'program', 'context': ...}
        uuid_order = []  # Track order of discovery
        
        def collect_uuids_with_context(data, path=""):
            if isinstance(data, dict):
                typename = str(data.get('__typename', ''))
                if 'uuid' in data:
                    uuid = data.get('uuid', '')
                    # Valid UUID format: has dashes and is 36 chars (32 hex + 4 dashes)
                    if uuid and '-' in uuid and len(uuid) == 36:
                        if uuid not in uuid_to_info:
                            info = {
                                'typename': typename,
                                'path': path,
                                'title': data.get('title', ''),
                                'order': len(uuid_order)
                            }
                            uuid_order.append(uuid)
                            # Determine type based on typename and context
                            if 'Clip' in typename or 'clip' in typename.lower():
                                info['type'] = 'clip'
                            elif 'Show' in typename or 'Program' in typename:
                                info['type'] = 'show'
                            elif 'title' in path.lower() or (data.get('title') and len(str(data.get('title', ''))) > 0):
                                # Title objects often contain clip UUIDs
                                info['type'] = 'clip'
                            else:
                                info['type'] = 'unknown'
                            uuid_to_info[uuid] = info
                
                for key, value in data.items():
                    # Skip very large lists to avoid performance issues
                    if isinstance(value, list) and len(value) > 2000:
                        continue
                    if isinstance(value, (dict, list)) and not isinstance(value, str):
                        collect_uuids_with_context(value, f"{path}.{key}" if path else key)
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    # Skip very large lists
                    if i > 1000:
                        break
                    if isinstance(item, (dict, list)):
                        collect_uuids_with_context(item, f"{path}[{i}]" if path else f"[{i}]")
        
        collect_uuids_with_context(json_data)
        
        # Find clip UUID and show UUID
        clip_uuid = None
        show_uuid = None
        all_uuids = list(uuid_to_info.keys())
        
        # The clip UUID is often associated with a title that has "uuid" in the JSON
        # Look for title objects with uuid - this is the clip ID
        def find_title_uuid(data):
            """Find UUID associated with episode title."""
            if isinstance(data, dict):
                # Check if this is a title object with uuid
                if 'title' in data and 'uuid' in data:
                    title_value = str(data.get('title', ''))
                    uuid_value = data.get('uuid', '')
                    # If title looks like episode title and has valid UUID
                    if uuid_value and '-' in uuid_value and len(uuid_value) > 30:
                        return uuid_value
                # Recursively search
                for value in data.values():
                    if isinstance(value, (dict, list)):
                        result = find_title_uuid(value)
                        if result:
                            return result
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        result = find_title_uuid(item)
                        if result:
                            return result
            return None
        
        # Try to find the clip UUID from title
        clip_uuid = find_title_uuid(json_data)
        
        # Prioritize UUIDs identified as clips
        for uuid, info in uuid_to_info.items():
            if info.get('type') == 'clip' and not clip_uuid:
                clip_uuid = uuid
            elif info.get('type') == 'show' and not show_uuid:
                show_uuid = uuid
        
        # If we found clip but not show, try to infer
        if clip_uuid and not show_uuid:
            # Show UUID is usually different from clip UUID
            # The show UUID is typically found earlier in the JSON structure
            for uuid in all_uuids:
                if uuid != clip_uuid:
                    show_uuid = uuid
                    break
        
        if not clip_uuid and len(all_uuids) >= 2:
            # Use the UUIDs in discovery order - first is often show, last is clip
            # Or try middle UUIDs if there are many
            if len(all_uuids) >= 3:
                # If we have 3+ UUIDs, use second as show and last as clip
                show_uuid = all_uuids[1] if len(all_uuids) > 2 else all_uuids[0]
                clip_uuid = all_uuids[-1]
            else:
                show_uuid = all_uuids[0]
                clip_uuid = all_uuids[-1]
        elif not clip_uuid and len(all_uuids) == 1:
            # Only one UUID found, try it as both show and clip
            clip_uuid = all_uuids[0]
            show_uuid = all_uuids[0]
        elif not clip_uuid:
            # No UUIDs found at all
            return None
        
        # Construct URL - we need showId and clipId
        if clip_uuid:
            if show_uuid and show_uuid != clip_uuid:
                url = f"https://traffic.omny.fm/d/clips/{org_id}/{show_uuid}/{clip_uuid}/audio.mp3"
                return url
            else:
                # If we only have clip UUID, try different combinations
                # Sometimes the show ID is the same as org ID or program ID
                # Try: orgId/showId/clipId where showId might be program-related
                # Try clip as both show and clip
                return f"https://traffic.omny.fm/d/clips/{org_id}/{clip_uuid}/{clip_uuid}/audio.mp3"
        
        return None
    
    def _find_omny_clip_reference(self, json_data):
        """Find Omny Studio clip reference in JSON data."""
        if isinstance(json_data, dict):
            if 'omnyStudioClip' in json_data:
                return json_data['omnyStudioClip']
            for value in json_data.values():
                result = self._find_omny_clip_reference(value)
                if result:
                    return result
        elif isinstance(json_data, list):
            for item in json_data:
                result = self._find_omny_clip_reference(item)
                if result:
                    return result
        return None
    
    def _find_image_by_ref(self, json_data, ref: str):
        """Find image object by reference (e.g., "Image:...")."""
        if not ref or not json_data:
            return None
        
        # Extract the ID part from reference (e.g., "Image:66dcbfda3ac847f6e76d534a")
        ref_id = ref.split(':')[-1] if ':' in ref else ref
        
        def find_by_ref_recursive(data):
            """Recursively find object with matching ID."""
            if isinstance(data, dict):
                # Check if this is the image object we're looking for
                obj_id = data.get('id', '')
                if obj_id == ref_id:
                    return data
                
                # Check __typename and id combination
                typename = data.get('__typename', '')
                if 'Image' in typename and obj_id == ref_id:
                    return data
                
                # Recursively search
                for value in data.values():
                    if isinstance(value, (dict, list)):
                        result = find_by_ref_recursive(value)
                        if result:
                            return result
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        result = find_by_ref_recursive(item)
                        if result:
                            return result
            return None
        
        return find_by_ref_recursive(json_data)
    
    def _find_programme_in_json(self, json_data, programme_slug: str):
        """Find programme object in JSON by slug."""
        if not programme_slug or not json_data:
            return None
        
        # Normalize the search term (extract just the slug part if it's a full URL)
        search_term = programme_slug
        if '/' in search_term:
            slug_match = re.search(r'/([^/]+)$', search_term)
            if slug_match:
                search_term = slug_match.group(1)
        
        def find_programme_recursive(data):
            """Recursively find programme object."""
            if isinstance(data, dict):
                # Check if this is a programme object (has 'title', 'slug', 'image')
                # Programmes have 'slug' but not 'airedAt' (episodes have 'airedAt')
                if 'slug' in data and 'title' in data and 'airedAt' not in data:
                    slug = data.get('slug', '')
                    # Match by slug (partial or exact)
                    if search_term in slug or slug == search_term or slug.endswith(search_term):
                        return data
                
                # Recursively search
                for value in data.values():
                    if isinstance(value, (dict, list)):
                        result = find_programme_recursive(value)
                        if result:
                            return result
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        result = find_programme_recursive(item)
                        if result:
                            return result
            return None
        
        return find_programme_recursive(json_data)
    
    def _is_generic_image(self, url: str) -> bool:
        """Check if image URL is a generic FBi Radio image (not programme-specific)."""
        if not url:
            return True
        
        # Normalize URL for comparison
        url_lower = url.lower()
        
        # Generic image patterns to exclude (only exclude truly generic FBi Radio images)
        # These are images that appear on many programme pages but aren't programme-specific
        generic_patterns = [
            'fbi-volunteers',  # Generic volunteer support image
            'supportfbi',      # Generic support FBi image
            'syd_images_web',  # Generic Sydney images
        ]
        
        # Extract filename from URL to check more precisely
        filename_match = re.search(r'/([^/]+)\.jpg', url_lower)
        if filename_match:
            filename = filename_match.group(1)
            # Check if filename starts with generic patterns
            for pattern in generic_patterns:
                if filename.startswith(pattern):
                    return True
        
        # Also check if pattern appears in URL path
        for pattern in generic_patterns:
            if f'/{pattern}' in url_lower:
                return True
        
        return False
    
    def extract_image_from_json(self, json_data):
        """Extract image URL from JSON data for programme icons.
        
        Args:
            json_data: JSON data structure
        
        Returns:
            Image URL or None
        """
        if not json_data:
            return None
        
        # URLs found during search
        found_urls = []
        
        def find_image_recursive(data):
            """Recursively find image objects in JSON."""
            if isinstance(data, dict):
                # Check if this is an Image object with sizes
                if 'sizes' in data:
                    sizes = data.get('sizes')
                    if isinstance(sizes, dict):
                        # Try programme icon sizes in priority order:
                        # wide_2000 (2000x1125), opengraph (1200x630), wide_800 (800x450)
                        for size_key in ['wide_2000', 'opengraph', 'wide_800', 'auto_2000', 'landscape_2000', 'auto_800', 'landscape_800']:
                            if size_key in sizes and isinstance(sizes[size_key], dict):
                                url = sizes[size_key].get('url')
                                if url and url.startswith('http'):
                                    found_urls.append((url, size_key))
                                    # Return immediately for high-priority sizes
                                    if size_key in ['wide_2000', 'opengraph', 'wide_800']:
                                        return url
                
                # Also check direct keys for sizes
                for size_key in ['wide_2000', 'opengraph', 'wide_800', 'auto_2000', 'landscape_2000', 'auto_800', 'landscape_800']:
                    if size_key in data:
                        size_obj = data[size_key]
                        if isinstance(size_obj, dict):
                            url = size_obj.get('url')
                            if url and url.startswith('http'):
                                found_urls.append((url, size_key))
                                # Return immediately for high-priority sizes
                                if size_key in ['wide_2000', 'opengraph', 'wide_800']:
                                    return url
                
                # Recursively search nested structures
                for value in data.values():
                    if isinstance(value, (dict, list)):
                        result = find_image_recursive(value)
                        if result:
                            return result
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        result = find_image_recursive(item)
                        if result:
                            return result
            return None
        
        result = find_image_recursive(json_data)
        
        # If we found URLs but didn't return early, use the first one
        if not result and found_urls:
            # Sort by preference: wide_2000 > opengraph > wide_800 > others
            preferred = ['wide_2000', 'opengraph', 'wide_800', 'auto_2000', 'landscape_2000', 'auto_800', 'landscape_800']
            
            for pref in preferred:
                for url, size in found_urls:
                    if size == pref:
                        return url
            
            # Return first URL found
            return found_urls[0][0]
        
        return result
    
    def extract_programme_image(self, html: str) -> Optional[str]:
        """Extract programme icon/image from programme page HTML.
        
        Returns:
            Image URL or None
        """
        # Check if we have a hardcoded override for this programme
        if self.program_slug in self.KNOWN_PROGRAMME_IMAGES:
            return self.KNOWN_PROGRAMME_IMAGES[self.program_slug]
        
        # First try extracting from JSON data - find the programme object specifically
        json_data = self.extract_json_data(html)
        if json_data:
            # Find the programme object in JSON (should have 'title', 'slug', and 'image')
            programme_obj = self._find_programme_in_json(json_data, self.program_slug)
            if programme_obj and programme_obj.get('image'):
                # Extract image from programme object
                image_ref = programme_obj.get('image')
                if isinstance(image_ref, dict):
                    if '__ref' in image_ref:
                        # Find image object by reference
                        ref = image_ref['__ref']
                        image_obj = self._find_image_by_ref(json_data, ref)
                        if image_obj:
                            image_url = self.extract_image_from_json(image_obj)
                            if image_url:
                                return image_url
                    else:
                        # Direct image object
                        image_url = self.extract_image_from_json(image_ref)
                        if image_url:
                            return image_url
            
            # Fallback: search JSON recursively if programme object not found
            image_url = self.extract_image_from_json(json_data)
            if image_url and not self._is_generic_image(image_url):
                return image_url
        
        # Fallback: search HTML for image URLs
        # Collect all matches first to prioritize correctly
        all_matches = []
        
        # Priority patterns for programme images:
        # 1. wide_2000 format (e.g., 2000x1125) - typical for programme icons
        # 2. opengraph format (e.g., 1200x630) - social media preview images
        # 3. wide format (e.g., 800x450) - smaller programme icons
        # These patterns need to handle URL-encoded spaces (%20) and regular spaces
        # Use .+? to match any characters including spaces and %20
        high_priority_patterns = [
            # Patterns for URLs in JSON (with quotes and url key)
            (r'"url"\s*:\s*"https://media\.fbi\.radio/images/[^"]+-2000x11\d{2}\.jpg"', ['wide_2000']),
            (r'"url"\s*:\s*"https://media\.fbi\.radio/images/[^"]+-1200x630\.jpg"', ['opengraph']),
            (r'"url"\s*:\s*"https://media\.fbi\.radio/images/[^"]+-800x450\.jpg"', ['wide_800']),
            # Patterns for bare URLs (can have spaces or %20)
            (r'https://media\.fbi\.radio/images/[^"\'\s\)]+-2000x11\d{2}\.jpg', ['wide_2000']),
            (r'https://media\.fbi\.radio/images/[^"\'\s\)]+-1200x630\.jpg', ['opengraph']),
            (r'https://media\.fbi\.radio/images/[^"\'\s\)]+-800x450\.jpg', ['wide_800']),
            # Patterns for URLs with URL-encoded spaces (%20)
            # Match %20 or spaces, handle multiple words
            (r'https://media\.fbi\.radio/images/.+?-2000x11\d{2}\.jpg', ['wide_2000']),
            (r'https://media\.fbi\.radio/images/.+?-1200x630\.jpg', ['opengraph']),
            (r'https://media\.fbi\.radio/images/.+?-800x450\.jpg', ['wide_800']),
        ]
        
        # First pass: look for high-priority programme icon sizes
        for pattern, labels in high_priority_patterns:
            matches = re.findall(pattern, html, re.I)
            for match in matches:
                # Extract URL from match
                if 'url' in match:
                    # Extract URL from JSON format: "url": "https://..."
                    url_match = re.search(r'"https://media\.fbi\.radio/images/[^"]+\.jpg"', match)
                    if url_match:
                        url = url_match.group(0).strip('"')
                        # Handle URL encoding (normalize spaces to %20)
                        url = url.replace(' ', '%20')
                        # Filter out generic images
                        if self._is_generic_image(url):
                            continue
                        # Only process if it matches our target sizes
                        if '-2000x11' in url or '-1200x630' in url or '-800x450' in url:
                            # Check if URL already in matches list
                            if url not in [m[0] for m in all_matches]:
                                all_matches.append((url, labels[0]))
                            # Return immediately if it's a high-priority format
                            if labels[0] in ['wide_2000', 'opengraph', 'wide_800']:
                                return url
                elif match.startswith('http'):
                    # Normalize spaces to %20 for consistency
                    url = match.replace(' ', '%20')
                    # Filter out generic images
                    if self._is_generic_image(url):
                        continue
                    # Only process if it matches our target sizes
                    if '-2000x11' in url or '-1200x630' in url or '-800x450' in url:
                        if url not in [m[0] for m in all_matches]:
                            all_matches.append((url, labels[0]))
                        # Return immediately if it's a high-priority format
                        if labels[0] in ['wide_2000', 'opengraph', 'wide_800']:
                            return url
        
        # If we found high-priority matches, return the first one (non-generic)
        if all_matches:
            # Sort by priority: wide_2000 > opengraph > wide_800
            priority_order = ['wide_2000', 'opengraph', 'wide_800']
            for priority in priority_order:
                for url, label in all_matches:
                    if label == priority and not self._is_generic_image(url):
                        return url
            # Return first non-generic match if no priority match found
            for url, label in all_matches:
                if not self._is_generic_image(url):
                    return url
            # Last resort: return first match even if generic
            if all_matches:
                return all_matches[0][0]
        
        # Second pass: look for any other programme images (fallback)
        fallback_patterns = [
            r'"url"\s*:\s*"https://media\.fbi\.radio/images/[^"]+\.jpg"',
            r'https://media\.fbi\.radio/images/[^"\'\s\)]+\.jpg',
        ]
        
        for pattern in fallback_patterns:
            matches = re.findall(pattern, html, re.I)
            for match in matches:
                if 'url' in match:
                    url_match = re.search(r'"https://media\.fbi\.radio/images/[^"]+\.jpg"', match)
                    if url_match:
                        url = url_match.group(0).strip('"').replace(' ', '%20')
                        # Filter out generic images
                        if self._is_generic_image(url):
                            continue
                        # Skip episode-specific images (smaller square formats)
                        # Prefer larger/wider images that are likely programme icons
                        if '-320x320' not in url and '-320x' not in url:
                            return url
                elif match.startswith('http'):
                    url = match.replace(' ', '%20')
                    # Filter out generic images
                    if self._is_generic_image(url):
                        continue
                    if '-320x320' not in url and '-320x' not in url:
                        return url
        
        return None
    
    def get_omny_audio_url(self, omny_clip_id, json_data: Optional[Dict] = None, html: Optional[str] = None) -> Optional[str]:
        """Construct Omny Studio direct audio URL from clip ID.
        
        URL format: https://traffic.omny.fm/d/clips/{orgId}/{showId}/{clipId}/audio.mp3
        """
        if not omny_clip_id:
            return None
        
        # Extract org ID from config
        org_id = None
        if html:
            config = self.extract_omny_config(html)
            org_id = config.get('orgId')
        
        # Default org ID if not found (from FBi Radio's config)
        if not org_id:
            org_id = "02b00798-16d7-4067-89ac-aba000ffd8cb"
        
        # Find clip UUID from the omny_clip_id reference
        clip_uuid = None
        
        # Handle different formats
        if isinstance(omny_clip_id, dict):
            clip_uuid = omny_clip_id.get('uuid', '')
            if not clip_uuid and json_data and '__ref' in omny_clip_id:
                ref = omny_clip_id.get('__ref', '')
                clip_uuid = self.find_uuid_in_data(json_data, ref)
        elif isinstance(omny_clip_id, (int, str)):
            # Try to find UUID in JSON data
            if json_data:
                clip_uuid = self.find_uuid_in_data(json_data)
        
        # If we still don't have clip UUID, search the entire JSON
        if not clip_uuid and json_data:
            clip_uuid = self.find_uuid_in_data(json_data)
        
        # Extract show ID - typically the program has an Omny show ID
        show_id = None
        if json_data:
            # Try to find show/program Omny ID in the structure
            show_id = self.find_uuid_in_data(json_data)  # This will get first UUID found
        
        # Construct the URL if we have the clip UUID
        if clip_uuid and org_id:
            # Need to get show ID - for now, try to extract from episode page
            # Format: /clips/{orgId}/{showId}/{clipId}/audio.mp3
            # If we don't have showId, we might need to fetch it from episode page
            if not show_id:
                # Try a different approach - look for the show ID in the JSON
                # The show ID is often associated with the program
                if isinstance(json_data, dict):
                    # Look for program-related UUIDs
                    for key, value in json_data.items():
                        if 'program' in key.lower() or 'show' in key.lower():
                            if isinstance(value, dict) and 'uuid' in value:
                                candidate = value.get('uuid')
                                if candidate and '-' in candidate:
                                    show_id = candidate
                                    break
            
            # If we still don't have show_id, we might need to fetch episode page
            # For now, construct URL without show_id (might need adjustment)
            if show_id:
                return f"https://traffic.omny.fm/d/clips/{org_id}/{show_id}/{clip_uuid}/audio.mp3"
            else:
                # Fallback: try without show ID (might not work, but worth trying)
                return f"https://traffic.omny.fm/d/clips/{org_id}/{clip_uuid}/audio.mp3"
        
        return None
    
    def parse_description(self, desc_obj) -> str:
        """Parse description from JSON structure."""
        if isinstance(desc_obj, dict):
            children = desc_obj.get('children', [])
            if children:
                # Extract text from children
                texts = []
                for child in children:
                    if isinstance(child, dict) and 'text' in child:
                        texts.append(child['text'])
                return ' '.join(texts)
        elif isinstance(desc_obj, str):
            return desc_obj
        return ""
    
    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string from ISO format or other formats."""
        if not date_str:
            return None
        
        # Try ISO format
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Ensure timezone-aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, AttributeError):
            pass
        
        # Try other formats
        date_patterns = [
            ('%Y-%m-%dT%H:%M:%S.%fZ', True),
            ('%Y-%m-%dT%H:%M:%SZ', True),
            ('%Y-%m-%d', False),
        ]
        
        for pattern, has_tz in date_patterns:
            try:
                dt = datetime.strptime(date_str, pattern)
                # Add UTC timezone if format had Z
                if has_tz:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    # Assume UTC for dates without timezone
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        
        return None
    
    def parse_date_from_url(self, url: str) -> Optional[datetime]:
        """Parse date from episode URL pattern like 'wildcard-with-stuart-coupe-28th-october-2025'."""
        if not url:
            return None
        
        # Pattern: episodes/wildcard-with-stuart-coupe-28th-october-2025
        # Extract date part: 28th-october-2025
        url_match = re.search(r'(\d{1,2})(?:st|nd|rd|th)-(\w+)-(\d{4})', url, re.I)
        if url_match:
            day = int(url_match.group(1))
            month_str = url_match.group(2).lower()
            year = int(url_match.group(3))
            
            # Convert month name to number
            months = {
                'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
                'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
                'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
                'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
            }
            
            month = months.get(month_str)
            if month:
                try:
                    dt = datetime(year, month, day, tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    # Invalid date (e.g., Feb 30)
                    return None
        
        return None
    
    def get_episodes(self) -> Tuple[List[Dict], str, Optional[str]]:
        """Get all episodes with their metadata.
        
        Returns:
            Tuple of (episodes list, program_name, program_image_url)
        """
        html = self.fetch_page(self.program_url)
        if not html:
            return [], self.program_slug, None
        
        soup = BeautifulSoup(html, 'lxml')
        program_name = soup.find('h1')
        program_name = program_name.get_text(strip=True) if program_name else self.program_slug
        
        # Extract programme image
        program_image = self.extract_programme_image(html)
        
        # Try to extract from JSON first
        json_data = self.extract_json_data(html)
        episodes_data = []
        
        if json_data:
            episodes_data = self.extract_episodes_from_json(json_data)
            # Store json_data for later use in resolving references
            for ep in episodes_data:
                ep['_json_data'] = json_data
        
        # Fallback: extract from HTML links
        if not episodes_data:
            episode_links = self.extract_episode_links_from_html(html)
            
            for i, episode_url in enumerate(episode_links, 1):
                episode_html = self.fetch_page(episode_url)
                if not episode_html:
                    continue
                
                episode_json = self.extract_json_data(episode_html)
                if episode_json:
                    episode_list = self.extract_episodes_from_json(episode_json)
                    if episode_list:
                        episodes_data.extend(episode_list)
                        continue
                
                # Fallback to HTML parsing
                episode_soup = BeautifulSoup(episode_html, 'lxml')
                title_elem = episode_soup.find('h1') or episode_soup.find('title')
                title = title_elem.get_text(strip=True) if title_elem else "Untitled Episode"
                
                # Try to find audio
                audio_url = None
                for script in episode_soup.find_all('script'):
                    if script.string and 'omny' in script.string.lower():
                        # Look for Omny Studio URLs
                        omny_match = re.search(r'https?://[^"\' ]+omny[^"\' ]+', script.string, re.I)
                        if omny_match:
                            audio_url = omny_match.group(0)
                
                # Extract date from URL
                episode_date = None
                url_match = re.search(r'(\d{1,2})[a-z]{2}-(\w+)-(\d{4})', episode_url)
                if url_match:
                    day, month_name, year = url_match.groups()
                    try:
                        month_num = datetime.strptime(month_name, '%B').month
                        episode_date = datetime(int(year), month_num, int(day), tzinfo=timezone.utc)
                    except ValueError:
                        pass
                
                episodes_data.append({
                    'title': title,
                    'url': episode_url,
                    'audio_url': audio_url,
                    'date': episode_date or datetime.now(timezone.utc),
                    'description': '',
                })
        
        # Process episodes - extract audio URLs and format
        episodes = []
        for ep in episodes_data:
            # Parse date - try airedAt first, then URL fallback
            episode_date = None
            aired_at = ep.get('airedAt', '')
            if aired_at:
                episode_date = self.parse_date(aired_at)
            
            # If no date from JSON, try to extract from URL
            if not episode_date and 'url' in ep:
                episode_date = self.parse_date_from_url(ep['url'])
            
            # Last resort: use current date (but this shouldn't happen)
            if not episode_date:
                episode_date = datetime.now(timezone.utc)
            
            # Parse description
            description = self.parse_description(ep.get('description', ''))
            
            # Get audio URL by fetching episode page
            audio_url = None
            if 'url' in ep:
                episode_html = self.fetch_page(ep['url'])
                if episode_html:
                    audio_url = self.extract_audio_url_from_episode_page(episode_html)
            
            episodes.append({
                'title': ep.get('title', 'Untitled Episode'),
                'url': ep.get('url', self.program_url),
                'audio_url': audio_url,
                'date': episode_date,
                'description': description,
            })
        
        # Sort by date (reverse chronological - newest first)
        # Filter out episodes without valid dates for sorting
        valid_episodes = [ep for ep in episodes if ep.get('date') is not None]
        episodes_without_dates = [ep for ep in episodes if ep.get('date') is None]
        
        # Sort valid episodes by date (newest first - reverse chronological)
        # Use timestamp for reliable sorting - ensure we're sorting by actual datetime objects
        def get_sort_key(ep):
            date = ep.get('date')
            if date is None:
                return 0
            # If it's a datetime object, use timestamp
            if hasattr(date, 'timestamp'):
                return date.timestamp()
            # Otherwise try to convert to timestamp
            try:
                return float(date)
            except (TypeError, ValueError):
                return 0
        
        valid_episodes.sort(key=get_sort_key, reverse=True)
        
        # Put episodes without dates at the end
        episodes = valid_episodes + episodes_without_dates
        return episodes, program_name, program_image


class RSSFeedGenerator:
    """Generate podcast RSS feeds from episode data."""
    
    def __init__(self, program_name: str, program_url: str):
        self.program_name = program_name
        self.program_url = program_url
    
    def generate_feed(self, episodes: List[Dict], output_file: str, program_image: Optional[str] = None):
        """Generate RSS feed file from episodes.
        
        Args:
            episodes: List of episode dictionaries
            output_file: Path to output RSS file
            program_image: URL to programme icon/image
        """
        fg = FeedGenerator()
        fg.title(self.program_name)
        fg.link(href=self.program_url, rel='alternate')
        fg.description(f'Podcast feed for {self.program_name} on FBi Radio')
        fg.language('en')
        fg.generator('fbi-to-rss')
        
        # Add programme image if available
        if program_image:
            fg.image(program_image)
            # Also add iTunes image for podcast compatibility
            fg.load_extension('podcast')
            try:
                fg.podcast.itunes_image(program_image)
            except:
                pass
        else:
            fg.load_extension('podcast')
        
        fg.podcast.itunes_category('Music')
        
        # Ensure episodes are sorted (feedgen might not preserve order)
        # Sort by pubDate in reverse chronological order (newest first)
        # IMPORTANT: feedgen preserves the order entries are added, so we MUST sort here
        def get_sort_timestamp(ep):
            date = ep.get('date')
            if date is None:
                # Put episodes without dates at the end
                return float('-inf')
            if hasattr(date, 'timestamp'):
                return date.timestamp()
            # Fallback for non-datetime dates
            try:
                return float(date)
            except (TypeError, ValueError):
                return float('-inf')
        
        # Sort in reverse chronological order (newest first)
        # reverse=True means larger timestamps (newer dates) come first
        sorted_episodes = sorted(episodes, key=get_sort_timestamp, reverse=True)
        
        # IMPORTANT: feedgen preserves the order entries are added
        # We must add entries in reverse chronological order (newest first)
        for episode in sorted_episodes:
            fe = fg.add_entry()
            fe.title(episode['title'])
            fe.link(href=episode['url'])
            fe.pubDate(episode['date'])
            
            if episode['description']:
                fe.description(episode['description'])
            
            # Add programme image to each episode entry
            if program_image:
                try:
                    fe.podcast.itunes_image(program_image)
                except:
                    pass
            
            # Add audio enclosure if available
            if episode.get('audio_url'):
                fe.enclosure(episode['audio_url'], 0, 'audio/mpeg')
            
            fe.id(episode['url'])
        
        # CRITICAL: feedgen may reorder entries by pubDate automatically when generating RSS
        # We'll generate the RSS as a string, parse it, reorder items, and write manually
        from xml.etree import ElementTree as ET
        from xml.dom import minidom
        
        # Generate RSS as string
        rss_str = fg.rss_str(pretty=True)
        
        # Parse the XML
        root = ET.fromstring(rss_str)
        
        # Find the channel element
        channel = root.find('channel')
        if channel is not None:
            # Get all item elements
            items = channel.findall('item')
            
            # Sort items by pubDate in reverse chronological order (newest first)
            def get_item_timestamp(item):
                pub_date_elem = item.find('pubDate')
                if pub_date_elem is not None and pub_date_elem.text:
                    try:
                        # Parse RFC 822 date format: "Sat, 01 Nov 2025 00:00:00 +0000"
                        from email.utils import parsedate_tz
                        date_tuple = parsedate_tz(pub_date_elem.text)
                        if date_tuple:
                            import time
                            timestamp = time.mktime(date_tuple[:9]) - (date_tuple[9] or 0)
                            return timestamp
                    except:
                        pass
                return 0
            
            # Sort items by date (newest first)
            items_sorted = sorted(items, key=get_item_timestamp, reverse=True)
            
            # Remove all items from channel
            for item in items:
                channel.remove(item)
            
            # Re-add items in sorted order (newest first)
            for item in items_sorted:
                channel.append(item)
        
        # Write the reordered XML
        # Convert back to string with proper formatting
        rough_string = ET.tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8')
        
        # Write to file
        with open(output_file, 'wb') as f:
            # Skip the XML declaration that minidom adds (we want just the content)
            lines = pretty_xml.decode('utf-8').split('\n')
            # Find where the actual RSS content starts (after <?xml...?>)
            content_start = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('<rss'):
                    content_start = i
                    break
            
            # Write from the RSS tag onwards
            content = '\n'.join(lines[content_start:])
            # Remove extra blank lines
            content = '\n'.join([line for line in content.split('\n') if line.strip() or line == ''])
            f.write(content.encode('utf-8'))
        print(f"Generated RSS feed: {output_file}")


def main():
    """Main entry point."""
    programs = [
        ('jack-off', 'Jack Off'),
        ('loose-joints', 'Loose Joints'),
        ('wildcard-with-stuart-coupe', 'Wildcard With Stuart Coupe'),
        ('sunset-with-tangela', 'Sunset with Tangela'),
        ('utility-fog', 'Utility Fog'),
    ]
    
    for program_slug, program_name in programs:
        print(f"\n{'='*60}")
        print(f"Processing: {program_name}")
        print(f"{'='*60}\n")
        
        scraper = FBIRadioScraper(program_slug)
        episodes, fetched_name, program_image = scraper.get_episodes()
        
        if not episodes:
            print(f"No episodes found for {program_name}")
            continue
        
        program_url = scraper.program_url
        output_file = f"{program_slug.replace('-', '_')}_feed.xml"
        
        generator = RSSFeedGenerator(fetched_name or program_name, program_url)
        generator.generate_feed(episodes, output_file, program_image)
        
        print(f"\n{len(episodes)} episodes processed for {program_name}")


if __name__ == '__main__':
    main()

