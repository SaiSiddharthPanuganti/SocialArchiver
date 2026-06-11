import csv
import os
import re
from datetime import datetime
from typing import List, Optional
from ingestion.base import BaseParser, SocialPost, UserProfile

class LinkedInParser(BaseParser):
    """Parses LinkedIn CSV data exports (Shares.csv, Comments.csv, Profile.csv)."""

    def _read_csv(self, file_path: str) -> List[dict]:
        """Helper to read CSV files with different potential encodings (UTF-8, UTF-8-sig, UTF-16)."""
        encodings = ['utf-8-sig', 'utf-8', 'utf-16', 'latin-1']
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    # Sniff dialect or use standard excel
                    sample = f.read(2048)
                    f.seek(0)
                    dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
                    # Ensure comma delimiter or let sniffer handle it
                    reader = csv.DictReader(f, dialect=dialect)
                    return [row for row in reader]
            except Exception:
                continue
        raise ValueError(f"Could not read LinkedIn CSV {file_path} with any supported encodings.")

    def parse(self, file_path: str) -> List[SocialPost]:
        """Parses Shares.csv or Comments.csv into SocialPosts."""
        filename = os.path.basename(file_path).lower()
        posts = []
        
        if not os.path.exists(file_path):
            return posts

        rows = self._read_csv(file_path)
        
        # Determine if it's Shares/Posts or Comments
        is_shares = "share" in filename or "post" in filename
        is_comments = "comment" in filename
        
        for idx, row in enumerate(rows):
            # Normalizing headers to lowercase for flexible matching
            normalized_row = {k.strip().lower() if k else "": v for k, v in row.items()}
            
            content = ""
            date_str = ""
            original_id = f"linkedin_{idx}"
            metadata = {}

            if is_shares:
                # LinkedIn Shares.csv headers: Date, ShareLink, ShareCommentary, SharedContentDescription, etc.
                content = normalized_row.get("sharecommentary") or normalized_row.get("content") or ""
                date_str = normalized_row.get("date") or ""
                share_link = normalized_row.get("sharelink") or ""
                original_id = share_link.split(":")[-1] if ":" in share_link else f"share_{idx}"
                metadata = {
                    "share_link": share_link,
                    "shared_content_desc": normalized_row.get("sharedcontentdescription") or "",
                    "visibility": normalized_row.get("visibility") or ""
                }
            elif is_comments:
                # LinkedIn Comments.csv headers: Date, CommentLink, Comment, etc.
                content = normalized_row.get("comment") or ""
                date_str = normalized_row.get("date") or ""
                comment_link = normalized_row.get("commentlink") or ""
                original_id = comment_link.split(":")[-1] if ":" in comment_link else f"comment_{idx}"
                metadata = {
                    "comment_link": comment_link,
                    "parent_link": normalized_row.get("commentparentlink") or ""
                }
            else:
                # Generic fallback if custom CSV loaded
                content = normalized_row.get("content") or normalized_row.get("text") or normalized_row.get("message") or ""
                date_str = normalized_row.get("date") or normalized_row.get("time") or normalized_row.get("timestamp") or ""
                
            if not content.strip():
                continue
                
            # Parse Date. LinkedIn exports typically use: YYYY-MM-DD HH:MM:SS or similar
            iso_timestamp = datetime.utcnow().isoformat()
            if date_str:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
                    try:
                        dt = datetime.strptime(date_str.strip(), fmt)
                        iso_timestamp = dt.isoformat()
                        break
                    except ValueError:
                        continue
                        
            posts.append(SocialPost(
                content=content.strip(),
                platform="linkedin",
                timestamp=iso_timestamp,
                author="User",  # Will be updated with profile details later if available
                original_id=original_id,
                source_file=os.path.basename(file_path),
                metadata=metadata
            ))
            
        return posts

    def parse_profile(self, file_path: str) -> Optional[UserProfile]:
        """Parses Profile.csv to fetch headline, summary, and name."""
        if not os.path.exists(file_path):
            return None
            
        try:
            rows = self._read_csv(file_path)
            if not rows:
                return None
            
            row = rows[0]
            normalized_row = {k.strip().lower() if k else "": v for k, v in row.items()}
            
            first_name = normalized_row.get("first name") or normalized_row.get("firstname") or ""
            last_name = normalized_row.get("last name") or normalized_row.get("lastname") or ""
            name = f"{first_name} {last_name}".strip() or "LinkedIn User"
            
            headline = normalized_row.get("headline") or ""
            summary = normalized_row.get("summary") or ""
            industry = normalized_row.get("industry") or ""
            
            return UserProfile(
                name=name,
                username=normalized_row.get("vanity name") or first_name.lower() or "linkedin_user",
                platform="linkedin",
                bio=f"{headline}\n\n{summary}".strip(),
                metadata={"industry": industry, "websites": normalized_row.get("websites") or ""}
            )
        except Exception as e:
            # Silently return default rather than blocking ingestion if profile parse fails
            return UserProfile(
                name="LinkedIn User",
                username="linkedin_user",
                platform="linkedin",
                bio="LinkedIn Professional Profile"
            )
