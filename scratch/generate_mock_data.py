import os
import csv
import json
import zipfile

def create_mock_data():
    # 1. Create a temporary folder structure for files
    base_dir = "./mock_data_files"
    os.makedirs(base_dir, exist_ok=True)
    
    # --- LINKEDIN EXPORT FILES ---
    # Shares.csv
    linkedin_shares = [
        ["Date", "ShareLink", "ShareCommentary", "SharedContentDescription", "SharedContentVisibility"],
        [
            "2023-08-15 10:00:00", 
            "urn:li:activity:7100000000000000001", 
            "Remote work isn't just a nice-to-have benefit; it is a massive productivity multiplier. Over the past 3 years, I have saved hundreds of hours by avoiding commutes. For software engineers, having blocks of uninterrupted focus time is critical. RTO mandates are a step backward. Remote-first organizations will attract the top talent because autonomy is the ultimate perk.",
            "Why Remote Work Wins", 
            "PUBLIC"
        ],
        [
            "2023-09-20 14:22:00", 
            "urn:li:activity:7100000000000000002", 
            "Had a great session building our new RAG engine today. ChromaDB and local embedding models (sentence-transformers) are doing wonders. Building LLM applications with a local-first design is so efficient. Looking forward to sharing our architecture next week!",
            "Building RAG Apps Locally", 
            "PUBLIC"
        ]
    ]
    with open(os.path.join(base_dir, "Shares.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(linkedin_shares)
        
    # Profile.csv
    linkedin_profile = [
        ["First Name", "Last Name", "Headline", "Summary", "Industry", "Websites"],
        ["Siddharth", "Sai", "Lead Software Architect | AI & RAG Specialist", "Designing and building high-performance decentralized systems, RAG chat apps, and multi-source ingestion pipelines. Believer in developer autonomy and remote work.", "Computer Software", "github.com/sai-siddharth"]
    ]
    with open(os.path.join(base_dir, "Profile.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(linkedin_profile)

    # --- TWITTER EXPORT FILES ---
    # tweets.js (with javascript prepend)
    tweets_content = [
        {
            "tweet": {
                "id_str": "1700000000000000001",
                "created_at": "Sat Sep 16 18:30:00 +0000 2023",
                "full_text": "Hot take: Open offices are a productivity nightmare. You cannot do deep, focused work when you hear 5 parallel conversations. Give software engineers remote options or private offices. #SoftwareEngineering #RemoteWork",
                "favorite_count": "142",
                "retweet_count": "24",
                "lang": "en"
            }
        },
        {
            "tweet": {
                "id_str": "1700000000000000002",
                "created_at": "Sun Sep 17 12:15:00 +0000 2023",
                "full_text": "RAG systems are only as good as their vector data schemas. Spend time on metadata design: timestamp, source platform, author, and specific segment IDs. Makes query filtering 10x faster. #AI #RAG",
                "favorite_count": "89",
                "retweet_count": "9",
                "lang": "en"
            }
        }
    ]
    with open(os.path.join(base_dir, "tweets.js"), "w", encoding="utf-8") as f:
        f.write("window.YTD.tweets.part0 = " + json.dumps(tweets_content, indent=2))
        
    # profile.js
    twitter_profile = [
        {
            "profile": {
                "description": {
                    "name": "Sai Siddharth",
                    "screenName": "sai_siddharth",
                    "bio": "Lead Software Architect writing about RAG systems, vector databases, and the future of remote developer work. Coding is lifestyle.",
                    "location": "India",
                    "website": "https://siddharth-architect.io"
                }
            }
        }
    ]
    with open(os.path.join(base_dir, "profile.js"), "w", encoding="utf-8") as f:
        f.write("window.YTD.profile.part0 = " + json.dumps(twitter_profile, indent=2))

    # --- INSTAGRAM EXPORT FILES ---
    # posts_1.json (using string_map_data structure)
    instagram_posts = [
        {
            "media_map_data": {},
            "string_map_data": {
                "Caption": {
                    "value": "Cozy cafe setup in Bali! 🌴💻 Working remotely is not just a location change; it is about finding the environment where your creativity thrives. Async meetings, good coffee, and lots of code today. #digitalnomad #remotework #balilife"
                },
                "Time": {
                    "timestamp": 1696118400  # 2023-10-01 00:00:00
                }
            }
        },
        {
            "media_map_data": {},
            "string_map_data": {
                "Caption": {
                    "value": "Wrote a custom python parser that unzips and ingests LinkedIn, Twitter, and Instagram archives in under 2 seconds. Clean code is beautiful code. Now building the front-end layout! #developer #rag #python"
                },
                "Time": {
                    "timestamp": 1696204800  # 2023-10-02 00:00:00
                }
            }
        }
    ]
    with open(os.path.join(base_dir, "posts_1.json"), "w", encoding="utf-8") as f:
        json.dump(instagram_posts, f, indent=2)
        
    # personal_information.json
    instagram_profile = {
        "profile_user_profile": {
            "username": "sai_siddharth_ig",
            "biography": "AI Architect & Digital Nomad. Building high-performance software. Currently working remotely.",
            "full_name": "Sai Siddharth"
        }
    }
    with open(os.path.join(base_dir, "personal_information.json"), "w", encoding="utf-8") as f:
        json.dump(instagram_profile, f, indent=2)

    # 2. Package everything into a single zip file in the root directory
    zip_filename = "mock_social_data_export.zip"
    
    # Remove existing zip if any
    if os.path.exists(zip_filename):
        os.remove(zip_filename)
        
    files_to_zip = [
        "Shares.csv", "Profile.csv", 
        "tweets.js", "profile.js", 
        "posts_1.json", "personal_information.json"
    ]
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files_to_zip:
            file_path = os.path.join(base_dir, file)
            if os.path.exists(file_path):
                # Write file directly into the ZIP root
                zipf.write(file_path, arcname=file)
                
    # 3. Clean up the folder files, leaving only the zip archive
    for file in files_to_zip:
        file_path = os.path.join(base_dir, file)
        if os.path.exists(file_path):
            os.remove(file_path)
    os.rmdir(base_dir)
    
    print(f"Successfully generated: {os.path.abspath(zip_filename)}")

if __name__ == "__main__":
    create_mock_data()
