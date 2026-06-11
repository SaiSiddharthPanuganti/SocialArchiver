from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class SocialPost(BaseModel):
    """Standardized representation of a single social media post, tweet, or message."""
    id: Optional[str] = Field(default=None, description="Unique, deterministic ID of the post")
    content: str = Field(..., description="The main text content of the post or message")
    platform: str = Field(..., description="Platform identifier (linkedin, twitter, instagram)")
    timestamp: str = Field(..., description="ISO 8601 formatted timestamp of the post")
    author: str = Field(..., description="Author of the content")
    original_id: str = Field(..., description="The original platform-specific ID of the post")
    source_file: str = Field(..., description="The source file from which this was parsed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Platform-specific metadata")

class UserProfile(BaseModel):
    """Standardized representation of user profile information across platforms."""
    name: str = Field(..., description="User's full name or screen name")
    username: str = Field(..., description="Platform-specific username or handle")
    platform: str = Field(..., description="Platform identifier (linkedin, twitter, instagram)")
    bio: Optional[str] = Field(None, description="Profile biography or summary")
    followers_count: Optional[int] = Field(None, description="Number of followers")
    following_count: Optional[int] = Field(None, description="Number of following")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional profile metadata")

class BaseParser(ABC):
    """Abstract base class for all platform-specific data parsers."""
    
    @abstractmethod
    def parse(self, file_path: str) -> List[SocialPost]:
        """Parse the input file and return a list of standardized SocialPost items."""
        pass
        
    @abstractmethod
    def parse_profile(self, file_path: str) -> Optional[UserProfile]:
        """Parse profile information from the input file if present."""
        pass
