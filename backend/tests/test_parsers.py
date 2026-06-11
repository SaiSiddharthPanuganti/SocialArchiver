import os
import json
import shutil
import tempfile
import unittest
from datetime import datetime
import sys
# Ensure backend directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.linkedin_parser import LinkedInParser
from ingestion.twitter_parser import TwitterParser
from ingestion.instagram_parser import InstagramParser
from ingestion.manager import IngestionManager


class TestParsers(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_linkedin_parser(self):
        # 1. Mock Shares.csv
        shares_path = os.path.join(self.temp_dir, "Shares.csv")
        with open(shares_path, "w", encoding="utf-8") as f:
            f.write("Date,ShareLink,ShareCommentary,SharedContentDescription,SharedContentVisibility\n")
            f.write("2023-05-10 14:30:00,urn:li:activity:7000000000000000000,Hello LinkedIn! Testing remote work thoughts.,A link description,PUBLIC\n")
            f.write("2023-06-11 09:15:00,urn:li:activity:7000000000000000001,,No commentary just link,PUBLIC\n") # Empty commentary should be ignored
            
        # 2. Mock Comments.csv
        comments_path = os.path.join(self.temp_dir, "Comments.csv")
        with open(comments_path, "w", encoding="utf-8") as f:
            f.write("Date,CommentLink,Comment,CommentParentLink\n")
            f.write("2023-05-12 18:45:00,urn:li:comment:123456,I disagree with that approach.,urn:li:activity:7000000000000000000\n")

        # 3. Mock Profile.csv
        profile_path = os.path.join(self.temp_dir, "Profile.csv")
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write("First Name,Last Name,Maiden Name,Address,Birth Date,Headline,Summary,Industry,Websites\n")
            f.write("Jane,Doe,,123 Main St,1990-01-01,AI Researcher,Building cool RAG agents,Tech,jane-doe.com\n")

        parser = LinkedInParser()
        
        # Test Shares parse
        shares = parser.parse(shares_path)
        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0].content, "Hello LinkedIn! Testing remote work thoughts.")
        self.assertEqual(shares[0].platform, "linkedin")
        self.assertEqual(shares[0].original_id, "7000000000000000000")
        
        # Test Comments parse
        comments = parser.parse(comments_path)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0].content, "I disagree with that approach.")
        self.assertEqual(comments[0].platform, "linkedin")
        self.assertEqual(comments[0].original_id, "123456")

        # Test Profile parse
        profile = parser.parse_profile(profile_path)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "Jane Doe")
        self.assertEqual(profile.platform, "linkedin")
        self.assertIn("AI Researcher", profile.bio)

    def test_twitter_parser(self):
        # 1. Mock tweets.js with JS window prepend
        tweets_path = os.path.join(self.temp_dir, "tweets.js")
        with open(tweets_path, "w", encoding="utf-8") as f:
            f.write("""window.YTD.tweets.part0 = [ {
  "tweet" : {
    "edit_info" : { "editTweetIds" : [ "1600000000000000000" ] },
    "retweeted" : false,
    "source" : "<a href=\\"http://twitter.com/download/iphone\\">Twitter for iPhone</a>",
    "entities" : { "user_mentions" : [ ], "urls" : [ ] },
    "favorite_count" : "42",
    "id_str" : "1600000000000000000",
    "retweet_count" : "12",
    "id" : "1600000000000000000",
    "created_at" : "Sat Dec 10 14:30:00 +0000 2022",
    "full_text" : "This is my original tweet about LLMs!",
    "lang" : "en"
  }
}, {
  "tweet" : {
    "retweeted" : true,
    "id_str" : "1600000000000000001",
    "created_at" : "Sun Dec 11 12:00:00 +0000 2022",
    "full_text" : "RT @someone_else: This is a retweet and should be filtered out.",
    "lang" : "en"
  }
} ]""")

        # 2. Mock profile.js
        profile_path = os.path.join(self.temp_dir, "profile.js")
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write("""window.YTD.profile.part0 = [ {
  "profile" : {
    "description" : {
      "bio" : "Twitter bio text",
      "website" : "http://twitter-jane.com",
      "location" : "San Francisco, CA",
      "name" : "Jane Twitter",
      "screenName" : "jane_tw"
    }
  }
} ]""")

        parser = TwitterParser()
        
        # Test Tweets parse (retweet should be filtered out)
        tweets = parser.parse(tweets_path)
        self.assertEqual(len(tweets), 1)
        self.assertEqual(tweets[0].content, "This is my original tweet about LLMs!")
        self.assertEqual(tweets[0].platform, "twitter")
        self.assertEqual(tweets[0].original_id, "1600000000000000000")
        self.assertEqual(tweets[0].metadata["favorite_count"], 42)

        # Test Profile parse
        profile = parser.parse_profile(profile_path)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "Jane Twitter")
        self.assertEqual(profile.username, "jane_tw")
        self.assertEqual(profile.bio, "Twitter bio text")

    def test_instagram_parser(self):
        # 1. Mock posts_1.json
        posts_path = os.path.join(self.temp_dir, "posts_1.json")
        with open(posts_path, "w", encoding="utf-8") as f:
            f.write(json.dumps([
                {
                    "media_map_data": {},
                    "string_map_data": {
                        "Caption": {
                            "value": "An awesome sunset in SF!"
                        },
                        "Time": {
                            "timestamp": 1672531200 # 2023-01-01 00:00:00 UTC
                        }
                    }
                },
                {
                    "media_map_data": {},
                    "string_map_data": {
                        "Time": {
                            "timestamp": 1672531200
                        }
                    } # Missing caption, should be ignored
                }
            ]))

        # 2. Mock posts.html
        posts_html_path = os.path.join(self.temp_dir, "posts.html")
        with open(posts_html_path, "w", encoding="utf-8") as f:
            f.write("""<html>
            <body>
                <div class="_a6-g">
                    <div>Caption in HTML!</div>
                    <div>Jan 1, 2023, 12:00 AM</div>
                </div>
            </body>
            </html>""")

        parser = InstagramParser()
        
        # Test JSON parse
        posts = parser.parse(posts_path)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].content, "An awesome sunset in SF!")
        self.assertEqual(posts[0].platform, "instagram")
        self.assertIn("2023-01-01", posts[0].timestamp)

        # Test HTML parse
        html_posts = parser.parse(posts_html_path)
        self.assertEqual(len(html_posts), 1)
        self.assertEqual(html_posts[0].content, "Caption in HTML!")
        self.assertEqual(html_posts[0].platform, "instagram")
        self.assertIn("2023-01-01", html_posts[0].timestamp)

    def test_manager_integration(self):
        # Setup complete mock archive directory
        os.makedirs(os.path.join(self.temp_dir, "linkedin"))
        os.makedirs(os.path.join(self.temp_dir, "twitter"))
        os.makedirs(os.path.join(self.temp_dir, "instagram"))
        
        # Write files
        with open(os.path.join(self.temp_dir, "linkedin", "Shares.csv"), "w", encoding="utf-8") as f:
            f.write("Date,ShareLink,ShareCommentary\n")
            f.write("2023-05-10 14:30:00,urn:li:activity:1,LinkedIn Post!\n")
            
        with open(os.path.join(self.temp_dir, "linkedin", "Profile.csv"), "w", encoding="utf-8") as f:
            f.write("First Name,Last Name,Headline\n")
            f.write("Alice,Smith,Dev\n")

        with open(os.path.join(self.temp_dir, "twitter", "tweets.js"), "w", encoding="utf-8") as f:
            f.write("""window.YTD.tweets.part0 = [ { "tweet" : { "id_str": "123", "full_text": "Tweet!", "created_at": "Sat Dec 10 14:30:00 +0000 2022" } } ]""")

        manager = IngestionManager()
        posts, profiles = manager.ingest_directory(self.temp_dir)
        
        # 1 LinkedIn post + 1 Twitter post = 2 posts total
        self.assertEqual(len(posts), 2)
        # Profile Alice Smith should enrich LinkedIn post author
        li_post = next(p for p in posts if p.platform == "linkedin")
        tw_post = next(p for p in posts if p.platform == "twitter")
        
        self.assertEqual(li_post.author, "Alice Smith")
        self.assertEqual(tw_post.author, "User")  # No twitter profile found, defaults to User
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].name, "Alice Smith")

if __name__ == "__main__":
    unittest.main()
