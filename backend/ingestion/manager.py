import os
import zipfile
import shutil
import tempfile
import re
from typing import List, Dict, Any, Tuple, Optional
from ingestion.base import SocialPost, UserProfile, BaseParser
from ingestion.linkedin_parser import LinkedInParser
from ingestion.twitter_parser import TwitterParser
from ingestion.instagram_parser import InstagramParser


class IngestionManager:
    """Manages multi-source ingestion of data exports, unzipping and routing to correct parsers."""
    
    def __init__(self):
        # Register platform-specific parsers
        self.parsers: Dict[str, BaseParser] = {
            "linkedin": LinkedInParser(),
            "twitter": TwitterParser(),
            "instagram": InstagramParser(),
        }
        
        # Define mapping rules: (regex pattern, platform, parser function name)
        # Matches against lowercase filenames
        self.file_rules: List[Tuple[str, str, str]] = [
            # LinkedIn
            (r"shares?\.csv$", "linkedin", "parse"),
            (r"comments?\.csv$", "linkedin", "parse"),
            (r"positions?\.csv$", "linkedin", "parse"),  # Parse job positions as source data if needed
            (r"profile?\.csv$", "linkedin", "parse_profile"),
            
            # Twitter / X
            (r"tweets?\.js$", "twitter", "parse"),
            (r"tweets?\.json$", "twitter", "parse"),
            (r"profile?\.js$", "twitter", "parse_profile"),
            
            # Instagram
            (r"posts_\d+\.json$", "instagram", "parse"),
            (r"posts?\.html$", "instagram", "parse"),
            (r"personal_information?\.json$", "instagram", "parse_profile"),
        ]

    def _match_file(self, filename: str) -> Optional[Tuple[str, str]]:
        """Matches a filename to a platform and action using regex rules."""
        fname_lower = filename.lower()
        for pattern, platform, action in self.file_rules:
            if re.search(pattern, fname_lower):
                return platform, action
        return None

    def ingest_directory(self, dir_path: str) -> Tuple[List[SocialPost], List[UserProfile]]:
        """Scans a directory for export files, parses them, and returns posts and profiles."""
        all_posts: List[SocialPost] = []
        profiles: List[UserProfile] = []
        
        # First pass: find profiles to associate author names with posts
        profile_map: Dict[str, UserProfile] = {}
        
        # Walk directory
        for root, _, files in os.walk(dir_path):
            for file in files:
                match = self._match_file(file)
                if not match:
                    continue
                
                platform, action = match
                file_path = os.path.join(root, file)
                parser = self.parsers.get(platform)
                
                if not parser:
                    continue

                if action == "parse_profile":
                    try:
                        profile = parser.parse_profile(file_path)
                        if profile:
                            profiles.append(profile)
                            profile_map[platform] = profile
                    except Exception as e:
                        print(f"Error parsing profile from {file} on {platform}: {e}")

        # Second pass: parse posts and apply profile names
        for root, _, files in os.walk(dir_path):
            for file in files:
                match = self._match_file(file)
                if not match:
                    continue
                
                platform, action = match
                file_path = os.path.join(root, file)
                parser = self.parsers.get(platform)
                
                if not parser:
                    continue

                if action == "parse":
                    try:
                        posts = parser.parse(file_path)
                        # Enrich author details
                        author_name = "User"
                        if platform in profile_map:
                            author_name = profile_map[platform].name
                            
                        for post in posts:
                            post.author = author_name
                            all_posts.append(post)
                    except Exception as e:
                        print(f"Error parsing posts from {file} on {platform}: {e}")

        return all_posts, profiles

    def ingest_zip(self, zip_path: str) -> Tuple[List[SocialPost], List[UserProfile]]:
        """Unzips a file to a temp directory, ingests the contents, and cleans up."""
        if not zipfile.is_zipfile(zip_path):
            # If it's a single file (not zip), copy to temp and ingest
            temp_dir = tempfile.mkdtemp()
            try:
                dest = os.path.join(temp_dir, os.path.basename(zip_path))
                shutil.copy(zip_path, dest)
                return self.ingest_directory(temp_dir)
            finally:
                shutil.rmtree(temp_dir)

        temp_dir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            return self.ingest_directory(temp_dir)
        finally:
            shutil.rmtree(temp_dir)
            
    def register_parser(self, platform: str, parser: BaseParser, rules: List[Tuple[str, str]]):
        """Allows dynamic registration of a new platform parser at runtime (e.g. for extensions)."""
        self.parsers[platform] = parser
        for pattern, action in rules:
            self.file_rules.append((pattern, platform, action))
