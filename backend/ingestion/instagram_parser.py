import json
import os
import re
from datetime import datetime
from typing import List, Optional
from bs4 import BeautifulSoup
from ingestion.base import BaseParser, SocialPost, UserProfile

class InstagramParser(BaseParser):
    """Parses Instagram data exports in both JSON format (e.g. posts_1.json) and HTML format."""

    def parse(self, file_path: str) -> List[SocialPost]:
        """Parses posts_1.json or posts.html into SocialPosts."""
        posts = []
        if not os.path.exists(file_path):
            return posts

        filename = os.path.basename(file_path).lower()
        
        # Check file extension
        if filename.endswith(".json"):
            posts = self._parse_json(file_path)
        elif filename.endswith(".html") or filename.endswith(".htm"):
            posts = self._parse_html(file_path)
            
        return posts

    def _parse_json(self, file_path: str) -> List[SocialPost]:
        """Parses Instagram JSON exports. Supports multiple structural formats."""
        posts = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            raise ValueError(f"Could not parse Instagram JSON {file_path}: {e}")

        # Instagram data exports usually present lists of media
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Try to find a list value (e.g. "media" or "posts")
            for key, val in data.items():
                if isinstance(val, list):
                    items = val
                    break
            if not items:
                items = [data]

        for idx, item in enumerate(items):
            content = ""
            timestamp_val = None
            original_id = f"instagram_{idx}"
            metadata = {}

            # Format 1: string_map_data (modern Meta export format)
            # { "media_map_data": ..., "string_map_data": { "Caption": { "value": "caption" }, "Time": { "timestamp": 12345 } } }
            if "string_map_data" in item:
                s_map = item["string_map_data"]
                if "Caption" in s_map:
                    content = s_map["Caption"].get("value") or ""
                if "Time" in s_map:
                    timestamp_val = s_map["Time"].get("timestamp")
                elif "Date" in s_map:
                    timestamp_val = s_map["Date"].get("timestamp")
                    
            # Format 2: simple title and creation_timestamp
            # { "title": "caption", "creation_timestamp": 12345 }
            elif "title" in item:
                content = item.get("title") or ""
                timestamp_val = item.get("creation_timestamp")
                
            # Format 3: nested media list
            # { "media": [{ "title": "caption", "creation_timestamp": 12345 }] }
            elif "media" in item and isinstance(item["media"], list):
                for sub_idx, sub_item in enumerate(item["media"]):
                    sub_posts = self._parse_json_item(sub_item, f"{original_id}_{sub_idx}", file_path)
                    posts.extend(sub_posts)
                continue

            # Skip empty content posts
            if not content.strip():
                continue

            iso_timestamp = self._parse_timestamp(timestamp_val)
            
            posts.append(SocialPost(
                content=content.strip(),
                platform="instagram",
                timestamp=iso_timestamp,
                author="User",
                original_id=original_id,
                source_file=os.path.basename(file_path),
                metadata=metadata
            ))

        return posts

    def _parse_json_item(self, item: dict, orig_id: str, source: str) -> List[SocialPost]:
        """Helper to parse a single media dictionary."""
        content = item.get("title") or ""
        timestamp_val = item.get("creation_timestamp")
        if not content.strip():
            return []
        iso_timestamp = self._parse_timestamp(timestamp_val)
        return [SocialPost(
            content=content.strip(),
            platform="instagram",
            timestamp=iso_timestamp,
            author="User",
            original_id=orig_id,
            source_file=os.path.basename(source),
            metadata={}
        )]

    def _parse_html(self, file_path: str) -> List[SocialPost]:
        """Parses Instagram HTML export pages using BeautifulSoup."""
        posts = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
        except Exception as e:
            raise ValueError(f"Could not parse Instagram HTML {file_path}: {e}")

        # Meta HTML exports usually place posts in divs with specific structure
        # Let's search for typical text containers and dates.
        # Often it is a list of blocks like `<div class="_a6-g">` or similar structure.
        # If classes are randomized, we can look at the raw divs.
        blocks = soup.find_all('div', class_=re.compile(r'(_a6-g|_a6-h|post-container)'))
        if not blocks:
            # Fallback: find all paragraphs and divs
            blocks = soup.find_all('div')

        for idx, block in enumerate(blocks):
            # Extract text
            text_nodes = block.find_all(text=True)
            text_content = [t.strip() for t in text_nodes if t.strip()]
            
            if not text_content:
                continue

            # Clean and look for timestamp and content
            content = ""
            date_str = ""
            
            # Instagram exports format: Dates often look like "Jan 1, 2023 12:00 PM"
            date_regex = re.compile(r'[A-Za-z]{3}\s\d{1,2},\s\d{4},\s\d{1,2}:\d{2}\s[A-Z]{2}')
            
            for text in text_content:
                if date_regex.match(text):
                    date_str = text
                elif len(text) > len(content) and not text.startswith("http"):
                    content = text

            if not content.strip() or len(content) < 3:
                continue

            iso_timestamp = datetime.utcnow().isoformat()
            if date_str:
                for fmt in ("%b %d, %Y, %I:%M %p", "%Y-%m-%d %H:%M:%S", "%b %d, %Y %H:%M:%S"):
                    try:
                        # Clean up text (non-breaking spaces, etc.)
                        clean_date = date_str.replace('\xa0', ' ').strip()
                        dt = datetime.strptime(clean_date, fmt)
                        iso_timestamp = dt.isoformat()
                        break
                    except ValueError:
                        continue

            posts.append(SocialPost(
                content=content.strip(),
                platform="instagram",
                timestamp=iso_timestamp,
                author="User",
                original_id=f"ig_html_{idx}",
                source_file=os.path.basename(file_path),
                metadata={}
            ))
            
        return posts

    def _parse_timestamp(self, ts_val) -> str:
        """Parses unix timestamp or string into ISO 8601 string."""
        if not ts_val:
            return datetime.utcnow().isoformat()
        try:
            # Check if it is a unix timestamp (seconds or milliseconds)
            ts = float(ts_val)
            if ts > 1e11:  # Milliseconds
                ts = ts / 1000.0
            return datetime.utcfromtimestamp(ts).isoformat()
        except (ValueError, TypeError):
            # Try to parse as string
            date_str = str(ts_val).strip()
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.isoformat()
                except ValueError:
                    continue
        return datetime.utcnow().isoformat()

    def parse_profile(self, file_path: str) -> Optional[UserProfile]:
        """Parses profile details from personal_information.json if present."""
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Instagram personal info format
            profile_data = {}
            if isinstance(data, list) and len(data) > 0:
                profile_data = data[0]
            elif isinstance(data, dict):
                profile_data = data
                
            # Try to search keys
            profile_dict = profile_data.get("profile_user_profile", profile_data)
            
            username = "instagram_user"
            bio = "Instagram Profile"
            name = "Instagram User"
            
            if "username" in profile_dict:
                username = profile_dict.get("username")
            if "biography" in profile_dict:
                bio = profile_dict.get("biography")
            if "full_name" in profile_dict:
                name = profile_dict.get("full_name")
                
            return UserProfile(
                name=name,
                username=username,
                platform="instagram",
                bio=bio,
                metadata={}
            )
        except Exception:
            return UserProfile(
                name="Instagram User",
                username="instagram_user",
                platform="instagram",
                bio="Instagram Profile"
            )
