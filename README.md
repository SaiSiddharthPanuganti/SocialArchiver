# Social Data Ingestion, Vector Knowledge Base & RAG Chat

A high-performance, beautiful end-to-end system that ingests personal social media archives (LinkedIn CSVs, Twitter/X JSON archives, and Instagram JSON/HTML), constructs a persistent vector knowledge base using **ChromaDB**, and provides a responsive cyberpunk dark-themed Web UI for grounded RAG (Retrieval-Augmented Generation) chat.

---

## 🏛️ Architecture Write-up

### 1. What does your system do, and what are the two or three most important architecture decisions you made?

This system processes personal social media archives to build a semantic knowledge base, allowing users to query a person's digital history (e.g., "What does this person think about remote work?") and get grounded answers with direct citations to original posts.
The three most critical architectural decisions were:
- **Local-First, Self-Contained Design (ChromaDB + Local Embeddings)**: We integrated **ChromaDB** in persistent mode and defaulted to local sentence-transformer embeddings (`all-MiniLM-L6-v2`). This allows the entire ingestion and search pipeline to run locally on the user's machine for free, without needing external databases, Docker setups, or SaaS API keys.
- **Asynchronous Background Ingestion Worker**: Ingestion of large exports (e.g., 50MB+ LinkedIn or Twitter archives) is decoupled from the FastAPI request/response loop using `BackgroundTasks`. This prevents HTTP timeouts, keeps the server responsive, and allows the React frontend to poll for real-time progress and logs.
- **Extensible Parser Engine Pattern**: Platform-specific parsers inherit from an abstract `BaseParser` class and are mapped dynamically via regex rules in `IngestionManager`. Adding a new platform (e.g., Facebook, Reddit) takes under an hour: simply write a parser, define its file matching rules, and register it.

### 2. Where is the bottleneck at 10x data volume? What breaks first?

At 10x data volume (hundreds of megabytes, hundreds of thousands of posts), the primary bottlenecks are **Memory Exhaustion during parsing** and **CPU Blocking during embedding computation**:
- **Memory Exhaustion**: Loading large JSON archives (like Twitter's `tweets.js` which can be 100MB+) completely into memory to parse it in Python will crash the process on memory-constrained systems.
- **CPU Blocking**: Embedding 10,000+ chunks sequentially on a CPU takes significant time. Because FastAPI's background task runner runs inside the main server process, long-running CPU-bound operations can block the event loop, causing API requests to stall or become sluggish.
- **SQLite Write Locks**: ChromaDB uses SQLite under the hood. Concurrently updating collections at high volumes will trigger database lock contentions.

To mitigate this, we would shift to streaming parsers (e.g., `ijson` for JSON, generator-based CSV reading), delegate embedding generation to an asynchronous distributed task queue (e.g., **Celery** with **Redis**), and leverage batch GPU embedding generation.

### 3. What did you consciously cut to stay in the 4 to 6 hour window, and what would you build next?

To deliver a high-quality end-to-end system within the time constraint, we consciously cut:
- **Deep Media Parsing & Nested Archives**: We focused on parsing authored posts, text comments, and profiles, and discarded media files (images, videos), messaging logs, and secondary metadata (ad receipt tracking, logins).
- **Asymmetric Threaded Chunking**: Chunking is currently done synchronously. We cut multi-threaded chunking to avoid complexity.
- **Tree-based Contextual Graphing**: We treated comments and posts as isolated documents with metadata link tags, instead of stitching them together into hierarchical conversation trees.
- **What we would build next**: 
  1. **ZIP Stream Filtering**: Instead of extracting the entire uploaded ZIP onto the disk (which is slow for huge archives containing many image assets), we would stream and parse *only* the matching CSV/JSON files directly from the ZIP memory buffer.
  2. **Conversational Memory**: Implement windowed session history in the RAG pipeline so the user can ask follow-up questions.
  3. **Visual Embeddings**: Parse and embed media caption context and run image-to-text descriptions on attachments.

### 4. If you had to make this architecture 10x better (not iterate on it, but rethink it), what would you change and why?

To make this architecture 10x better, we would transition to a **GraphRAG (Knowledge Graph + Vector Hybrid) Architecture** running on an event-driven serverless pipeline.
- **Why?** Social media content is deeply relational: a tweet is a reply to another tweet; a LinkedIn post tags a company; a comment responds to a specific paragraph. Converting this relational web into flat vector chunks loses the core context. By parsing archives directly into a Graph Database (like **Neo4j** or **Memgraph**) paired with vector properties (GraphRAG), the system could run hybrid queries.
- **How?** During a query, the LLM wouldn't just fetch isolated semantic chunks; it would fetch the *entire conversation tree* and *related entity relationships* (e.g., "Find posts from 2023 discussing Remote Work, and include the company entities mentioned"). Ingestion would be processed using serverless functions (like AWS Lambda) that scale horizontally to parse and embed thousands of files in parallel, uploading to a managed vector graph database.

---

## 🛠️ Project Structure

```
├── backend/
│   ├── database/
│   │   ├── embeddings.py      # Embedding configurations (Local/OpenAI)
│   │   ├── llm.py             # LLM stream completions (Gemini/OpenAI)
│   │   └── vector_store.py    # ChromaDB connection & intelligent chunking
│   ├── Ingestion/
│   │   ├── base.py            # Pydantic schemas & BaseParser
│   │   ├── linkedin_parser.py # LinkedIn CSV shares, comments, profile parser
│   │   ├── twitter_parser.py  # Twitter JS prefix stripper & JSON archive parser
│   │   ├── instagram_parser.py# Instagram JSON & BeautifulSoup HTML parser
│   │   └── manager.py         # Multi-platform ingestion coordinator
│   ├── Tests/
│   │   └── test_parsers.py    # Unit tests for ingestion
│   ├── config.json            # Persistent UI configuration
│   ├── requirements.txt       # Python backend dependencies
│   └── main.py                # FastAPI endpoints & background workers
├── frontend/
│   ├── src/
│   │   ├── App.tsx            # Main RAG Dashboard & Chat Panel
│   │   ├── index.css          # Cyberpunk dark styling
│   │   └── main.tsx           # React entry point
│   ├── package.json           # Node dependencies
│   ├── vite.config.ts         # Vite server configuration
│   └── index.html             # HTML entry template (with SEO meta tags)
├── .env.example               # Environmental configuration guide
└── README.md                  # System documentation
```

---

## ⚡ Quick Start Guide

### Prerequisites
- Python 3.10+
- Node.js v18+ & npm

---

### 1. Run the Backend Server (FastAPI)

1. Open a terminal and navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Install python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the uvicorn development server:
   ```bash
   uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```
   *The API server will run on `http://localhost:8000`. Swagger docs are available at `http://localhost:8000/docs`.*

---

### 2. Run the Frontend (React + Vite)

1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install Node packages (already completed if dependencies were scaffolded):
   ```bash
   npm install
   ```

3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   *The Web UI will be available at `http://localhost:5173`.*

---

## 🧪 Running Tests
We have implemented a comprehensive test suite that creates mock data exports and asserts parser outputs. To execute from the root directory:
```bash
python backend/tests/test_parsers.py
```
Or from the backend directory:
```bash
python tests/test_parsers.py
```


---

## ⚙️ Configuration & RAG Usage
1. Open the UI at `http://localhost:5173`.
2. On the **API & Model Config** sidebar, enter your API Keys:
   - **Gemini 2.0 Flash (Default)**: Enter your API Key.
   - **Groq**:Enter your API Key.
   - **OpenAI**: Enter your OpenAI API Key and select it in the dropdown.
3. Click **Save Config**.
4. In the **Ingest Data Export** section, drag-and-drop or click to upload your data export archive (`.zip` or individual files).
5. Watch the real-time background processing bar finish.
6. Start chatting! The assistant will stream answers and display a collapsible list of cited original posts.
