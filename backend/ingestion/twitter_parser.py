import json
import os
import re
from datetime import datetime
from typing import List, Optional, Any
from ingestion.base import BaseParser, SocialPost, UserProfile

class TwitterParser(BaseParser):
    """Parses Twitter/X export archives (tweets.js, tweet.js, profile.js)."""

    def _strip_js_prefix(self, content: str) -> str:
        """Strips 'window.YTD.tweets.part0 = ' or similar javascript prefixes to get raw JSON."""
        # Find the first index of '[' or '{'
        match = re.search(r'[\{\[]', content)
        if match:
            return content[match.start():]
        return content

    def _load_json_file(self, file_path: str) -> Any:
        """Reads a file, strips JS variables, and parses JSON."""
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        
        json_str = self._strip_js_prefix(raw_content)
        # Handle trailing semicolons or JS garbage
        json_str = json_str.strip().rstrip(';')
        return json.loads(json_str)

    def parse(self, file_path: str) -> List[SocialPost]:
        """Parses tweets.js or tweet.js into SocialPosts."""
        posts = []
        if not os.path.exists(file_path):
            return posts

        try:
            data = self._load_json_file(file_path)
        except Exception as e:
            # Fallback for plain JSON files
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e2:
                raise ValueError(f"Could not parse Twitter file {file_path} as JSON: {e2}")

        # Twitter exports contain a list of objects: [{"tweet": {...}}] or just list of tweets
        tweet_list = []
        if isinstance(data, list):
            tweet_list = data
        elif isinstance(data, dict):
            # Sometimes exports are dicts, check if there's a list inside
            for val in data.values():
                if isinstance(val, list):
                    tweet_list = val
                    break

        for idx, item in enumerate(tweet_list):
            tweet_data = item.get("tweet") if isinstance(item, dict) and "tweet" in item else item
            if not isinstance(tweet_data, dict):
                continue

            content = tweet_data.get("full_text") or tweet_data.get("text") or ""
            
            # Efficiency / Noise Filter: Skip direct retweets (starts with RT @)
            # We want content that *actually represents the person* (authored content)
            if content.startswith("RT @"):
                continue

            original_id = tweet_data.get("id_str") or str(tweet_data.get("id", f"tweet_{idx}"))
            date_str = tweet_data.get("created_at") or ""
            
            # Twitter created_at format: "Wed Aug 29 17:12:58 +0000 2012"
            iso_timestamp = datetime.utcnow().isoformat()
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")
                    iso_timestamp = dt.isoformat()
                except ValueError:
                    try:
                        # Fallback for other formats
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        iso_timestamp = dt.isoformat()
                    except ValueError:
                        pass

            likes = int(tweet_data.get("favorite_count", 0))
            retweets = int(tweet_data.get("retweet_count", 0))
            
            metadata = {
                "favorite_count": likes,
                "retweet_count": retweets,
                "lang": tweet_data.get("lang", ""),
                "in_reply_to_status_id": tweet_data.get("in_reply_to_status_id_str") or ""
            }

            posts.append(SocialPost(
                content=content.strip(),
                platform="twitter",
                timestamp=iso_timestamp,
                author="User",  # Will be updated with profile details later
                original_id=original_id,
                source_file=os.path.basename(file_path),
                metadata=metadata
            ))

        return posts

    def parse_profile(self, file_path: str) -> Optional[UserProfile]:
        """Parses profile.js into UserProfile."""
        if not os.path.exists(file_path):
            return None

        try:
            data = self._load_json_file(file_path)
            
            profile_data = {}
            if isinstance(data, list) and len(data) > 0:
                profile_data = data[0].get("profile", data[0])
            elif isinstance(data, dict):
                profile_data = data.get("profile", data)
                
            name = profile_data.get("description", {}).get("name") or "Twitter User"
            username = profile_data.get("description", {}).get("screenName") or "twitter_user"
            bio = profile_data.get("description", {}).get("bio") or ""
            
            return UserProfile(
                name=name,
                username=username,
                platform="twitter",
                bio=bio,
                metadata={
                    "location": profile_data.get("description", {}).get("location") or "",
                    "website": profile_data.get("description", {}).get("website") or ""
                }
            )
        except Exception as e:
            return UserProfile(
                name="Twitter User",
                username="twitter_user",
                platform="twitter",
                bio="Twitter / X Profile"
            )
