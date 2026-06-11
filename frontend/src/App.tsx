import React, { useState, useEffect, useRef } from 'react';

// API base URL pointing to FastAPI
const API_BASE = "/api";

interface Citation {
  index: number;
  platform: string;
  timestamp: string;
  author: string;
  original_id: string;
  snippet: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  loading?: boolean;
}

interface PlatformCounts {
  linkedin: number;
  twitter: number;
  instagram: number;
}

interface TypeCounts {
  post: number;
  profile: number;
}

interface Stats {
  total_chunks: number;
  platform_counts: PlatformCounts;
  type_counts: TypeCounts;
}

interface IngestStatus {
  status: 'idle' | 'processing' | 'completed' | 'failed';
  progress: number;
  current_step: string;
  total_posts: number;
  total_chunks: number;
  error: string | null;
}

export default function App() {
  // Config & Settings State
  const [llmProvider, setLlmProvider] = useState<'openai' | 'gemini' | 'local' | 'groq'>('local');
  const [embeddingProvider, setEmbeddingProvider] = useState<'local' | 'openai'>('local');
  const [openaiApiKey, setOpenaiApiKey] = useState('');
  const [geminiApiKey, setGeminiApiKey] = useState('');
  const [groqApiKey, setGroqApiKey] = useState('');
  const [maskedOpenaiKey, setMaskedOpenaiKey] = useState('');
  const [maskedGeminiKey, setMaskedGeminiKey] = useState('');
  const [maskedGroqKey, setMaskedGroqKey] = useState('');
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);

  // Stats State
  const [stats, setStats] = useState<Stats>({
    total_chunks: 0,
    platform_counts: { linkedin: 0, twitter: 0, instagram: 0 },
    type_counts: { post: 0, profile: 0 }
  });
  const [loadingStats, setLoadingStats] = useState(false);

  // Ingestion State
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [ingestStatus, setIngestStatus] = useState<IngestStatus>({
    status: 'idle',
    progress: 0,
    current_step: '',
    total_posts: 0,
    total_chunks: 0,
    error: null
  });

  // Chat State
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [filterPlatform, setFilterPlatform] = useState<'all' | 'linkedin' | 'twitter' | 'instagram'>('all');
  const [openCitations, setOpenCitations] = useState<Record<string, boolean>>({});

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const pollingIntervalRef = useRef<number | null>(null);

  // Load configuration and database stats on mount
  useEffect(() => {
    fetchSettings();
    fetchStats();
    checkActiveIngestion();
    return () => {
      if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current);
    };
  }, []);

  // Scroll chat to bottom on new messages and citation toggles
  useEffect(() => {
    const timer = setTimeout(() => {
      chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, 80);
    return () => clearTimeout(timer);
  }, [messages, chatLoading, openCitations]);

  const fetchSettings = async () => {
    try {
      const res = await fetch(`${API_BASE}/settings`);
      if (res.ok) {
        const data = await res.json();
        setLlmProvider(data.llm_provider);
        setEmbeddingProvider(data.embedding_provider);
        setMaskedOpenaiKey(data.masked_openai_key);
        setMaskedGeminiKey(data.masked_gemini_key);
        setMaskedGroqKey(data.masked_groq_key);
      }
    } catch (e) {
      console.error("Failed to load settings:", e);
    }
  };

  const saveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingSettings(true);
    setSettingsSaved(false);
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          llm_provider: llmProvider,
          embedding_provider: embeddingProvider,
          openai_api_key: openaiApiKey || null,
          gemini_api_key: geminiApiKey || null,
          groq_api_key: groqApiKey || null
        })
      });
      if (res.ok) {
        setSettingsSaved(true);
        setOpenaiApiKey('');
        setGeminiApiKey('');
        setGroqApiKey('');
        await fetchSettings();
        // Hide success mark after 3s
        setTimeout(() => setSettingsSaved(false), 3000);
      }
    } catch (e) {
      console.error("Failed to save settings:", e);
    } finally {
      setSavingSettings(false);
    }
  };

  const fetchStats = async () => {
    setLoadingStats(true);
    try {
      const res = await fetch(`${API_BASE}/ingest/stats`);
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error("Failed to fetch stats:", e);
    } finally {
      setLoadingStats(false);
    }
  };

  const checkActiveIngestion = async () => {
    try {
      const res = await fetch(`${API_BASE}/ingest/status`);
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'processing') {
          setIngestStatus(data);
          startStatusPolling();
        }
      }
    } catch (e) {
      console.error("Failed to check active ingestion:", e);
    }
  };

  const startStatusPolling = () => {
    if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current);
    
    pollingIntervalRef.current = window.setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/ingest/status`);
        if (res.ok) {
          const data = await res.json();
          setIngestStatus(data);
          if (data.status === 'completed' || data.status === 'failed') {
            if (pollingIntervalRef.current) {
              clearInterval(pollingIntervalRef.current);
              pollingIntervalRef.current = null;
            }
            fetchStats(); // Refresh database stats
          }
        }
      } catch (e) {
        console.error("Error polling ingestion status:", e);
      }
    }, 1500);
  };

  const handleFileUpload = async (file: File) => {
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE}/ingest/upload`, {
        method: 'POST',
        body: formData
      });
      if (res.ok) {
        setIngestStatus({
          status: 'processing',
          progress: 5,
          current_step: 'Uploading file...',
          total_posts: 0,
          total_chunks: 0,
          error: null
        });
        startStatusPolling();
      } else {
        const err = await res.json();
        alert(`Upload failed: ${err.detail || 'Unknown error'}`);
      }
    } catch (e) {
      console.error("Error uploading file:", e);
      alert("Network error uploading file.");
    } finally {
      setUploading(false);
    }
  };

  const triggerClearDatabase = async () => {
    if (!confirm("Are you sure you want to wipe the vector knowledge base? This action cannot be undone.")) {
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/clear`, { method: 'POST' });
      if (res.ok) {
        fetchStats();
        setMessages([]);
        alert("Database cleared successfully.");
      }
    } catch (e) {
      console.error("Failed to clear database:", e);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = () => {
    setDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFileUpload(files[0]);
    }
  };

  const handleChatSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || chatLoading) return;

    const userText = inputValue;
    setInputValue('');
    setChatLoading(true);

    const userMsgId = Date.now().toString();
    const assistantMsgId = (Date.now() + 1).toString();

    // 1. Add User Message
    const userMsg: Message = { id: userMsgId, role: 'user', content: userText };
    setMessages(prev => [...prev, userMsg]);

    // 2. Add empty Assistant Message placeholder
    const assistantMsg: Message = { id: assistantMsgId, role: 'assistant', content: '', citations: [], loading: true };
    setMessages(prev => [...prev, assistantMsg]);

    try {
      // 3. Make RAG Streaming call
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: userText,
          top_k: 5,
          platform: filterPlatform === 'all' ? null : filterPlatform
        })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Server error running query.");
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      if (!reader) throw new Error("Response body is not readable.");

      let buffer = "";
      let citations: Citation[] = [];
      let isReadingMetadata = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const decodedChunk = decoder.decode(value, { stream: true });
        buffer += decodedChunk;

        // Process custom citations metadata prefix
        if (buffer.includes("METADATA_START\n")) {
          isReadingMetadata = true;
          buffer = buffer.substring(buffer.indexOf("METADATA_START\n") + "METADATA_START\n".length);
        }

        if (isReadingMetadata && buffer.includes("METADATA_END\n\n")) {
          const splitIndex = buffer.indexOf("METADATA_END\n\n");
          const metaText = buffer.substring(0, splitIndex).trim();
          buffer = buffer.substring(splitIndex + "METADATA_END\n\n".length);
          isReadingMetadata = false;

          try {
            const parsedMeta = JSON.parse(metaText);
            citations = parsedMeta.citations || [];
            setMessages(prev => prev.map(msg => 
              msg.id === assistantMsgId ? { ...msg, citations } : msg
            ));
          } catch (e) {
            console.error("Error parsing citations block:", e);
          }
        }

        // Stream remaining text to content
        if (!isReadingMetadata && buffer.length > 0) {
          const textToAppend = buffer;
          buffer = ""; // clear buffer
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMsgId ? { ...msg, content: msg.content + textToAppend, loading: false } : msg
          ));
        }
      }
      
      // Stop loading spinner
      setMessages(prev => prev.map(msg => 
        msg.id === assistantMsgId ? { ...msg, loading: false } : msg
      ));

    } catch (e: any) {
      console.error(e);
      setMessages(prev => prev.map(msg => 
        msg.id === assistantMsgId ? { 
          ...msg, 
          content: `Failed to get response. ${e.message || 'Check backend server and API keys settings.'}`, 
          loading: false 
        } : msg
      ));
    } finally {
      setChatLoading(false);
    }
  };

  const toggleCitations = (msgId: string) => {
    setOpenCitations(prev => ({
      ...prev,
      [msgId]: !prev[msgId]
    }));
  };

  const triggerSuggestionClick = (query: string) => {
    setInputValue(query);
  };

  return (
    <div className="app-container">
      {/* Sidebar Panel */}
      <aside className="sidebar">
        <div className="logo-container">
          <div className="logo-icon">S</div>
          <div className="logo-text">SocialArchiver</div>
        </div>

        {/* Dynamic Settings Panel */}
        <section className="glass-panel">
          <h3 className="section-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.1a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle></svg>
            API & Model Config
          </h3>
          <form onSubmit={saveSettings}>
            <div className="form-group">
              <label>LLM Engine</label>
              <select value={llmProvider} onChange={e => setLlmProvider(e.target.value as any)}>
                <option value="local">Gemini 2.0 Flash (Free Cloud LLM)</option>
                <option value="groq">Groq (Llama 3.3 70B - Ultra Fast)</option>
                <option value="openai">OpenAI (GPT-4o-mini)</option>
              </select>
            </div>

            <div className="form-group">
              <label>Embedding Engine</label>
              <select value={embeddingProvider} onChange={e => setEmbeddingProvider(e.target.value as any)}>
                <option value="local">Local (all-MiniLM-L6-v2) - Free</option>
                <option value="openai">OpenAI (text-embedding-3-small)</option>
              </select>
            </div>

            {llmProvider === 'openai' || embeddingProvider === 'openai' ? (
              <div className="form-group">
                <label>API Key</label>
                <input 
                  type="password" 
                  value={openaiApiKey}
                  onChange={e => setOpenaiApiKey(e.target.value)}
                  placeholder={maskedOpenaiKey ? `${maskedOpenaiKey} (Configured)` : "sk-..."}
                />
              </div>
            ) : null}

            {llmProvider === 'local' || llmProvider === 'gemini' ? (
              <div className="form-group">
                <label>API Key</label>
                <input 
                  type="password" 
                  value={geminiApiKey}
                  onChange={e => setGeminiApiKey(e.target.value)}
                  placeholder={maskedGeminiKey ? `${maskedGeminiKey} (Configured)` : "AIzaSy..."}
                />
              </div>
            ) : null}

            {llmProvider === 'groq' ? (
              <div className="form-group">
                <label>API Key</label>
                <input 
                  type="password" 
                  value={groqApiKey}
                  onChange={e => setGroqApiKey(e.target.value)}
                  placeholder={maskedGroqKey ? `${maskedGroqKey} (Configured)` : "gsk_..."}
                />
              </div>
            ) : null}

            <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '8px' }} disabled={savingSettings}>
              {savingSettings ? <div className="spinner"></div> : settingsSaved ? 'Settings Saved! ✓' : 'Save Config'}
            </button>
          </form>
        </section>

        {/* Database statistics card */}
        <section className="glass-panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 className="section-title" style={{ margin: 0 }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M3 5V19A9 3 0 0 0 21 19V5"></path><path d="M3 12A9 3 0 0 0 21 12"></path></svg>
              Knowledge Base
            </h3>
            <button className="stats-refresh-btn" onClick={fetchStats} disabled={loadingStats}>
              <svg className={loadingStats ? 'spin' : ''} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path></svg>
            </button>
          </div>

          <div className="stats-grid">
            <div className="stat-item">
              <span className="stat-num linkedin">{stats.platform_counts.linkedin}</span>
              <span className="stat-label">LinkedIn</span>
            </div>
            <div className="stat-item">
              <span className="stat-num twitter">{stats.platform_counts.twitter}</span>
              <span className="stat-label">Twitter/X</span>
            </div>
            <div className="stat-item">
              <span className="stat-num instagram">{stats.platform_counts.instagram}</span>
              <span className="stat-label">Instagram</span>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '16px', borderTop: '1px solid var(--border-color)', paddingTop: '12px' }}>
            <span>Total Vector Chunks:</span>
            <span style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>{stats.total_chunks}</span>
          </div>

          {stats.total_chunks > 0 && (
            <button onClick={triggerClearDatabase} className="btn btn-danger" style={{ width: '100%', marginTop: '16px', fontSize: '0.8rem', padding: '8px' }}>
              Clear Knowledge Base
            </button>
          )}
        </section>

        {/* Data export Ingestion panel */}
        <section className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <h3 className="section-title" style={{ margin: 0 }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
            Ingest Data Export
          </h3>

          <div 
            className={`upload-zone ${dragging ? 'dragging' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input 
              type="file" 
              ref={fileInputRef} 
              style={{ display: 'none' }} 
              accept=".zip,.csv,.js,.json,.html"
              onChange={e => e.target.files && handleFileUpload(e.target.files[0])}
            />
            <div className="upload-icon">
              {uploading ? (
                <div className="spinner" style={{ width: '30px', height: '30px' }}></div>
              ) : (
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
              )}
            </div>
            <div className="upload-text">
              {uploading ? 'Uploading File...' : 'Drop ZIP or Archive files here'}
            </div>
            <div className="upload-subtext">Supports LinkedIn, X, and Instagram exports</div>
          </div>

          {ingestStatus.status === 'processing' && (
            <div className="progress-container">
              <div className="progress-info">
                <span className="progress-step">{ingestStatus.current_step}</span>
                <span className="progress-percent">{ingestStatus.progress}%</span>
              </div>
              <div className="progress-bar-bg">
                <div className="progress-bar-fill" style={{ width: `${ingestStatus.progress}%` }}></div>
              </div>
            </div>
          )}

          {ingestStatus.status === 'completed' && (
            <div style={{ color: 'var(--color-success)', fontSize: '0.8rem', textAlign: 'center', background: 'rgba(16, 185, 129, 0.1)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
              Ingested {ingestStatus.total_posts} posts into {ingestStatus.total_chunks} vector chunks!
            </div>
          )}

          {ingestStatus.status === 'failed' && (
            <div style={{ color: 'var(--color-error)', fontSize: '0.8rem', textAlign: 'center', background: 'rgba(239, 68, 68, 0.1)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
              Ingestion Failed: {ingestStatus.error}
            </div>
          )}
        </section>
      </aside>

      {/* Main RAG Chat Panel */}
      <main className="chat-main">
        <header className="chat-header">
          <div className="chat-title-group">
            <h2 className="chat-title">Personal Social Brain</h2>
            <p className="chat-subtitle">Ask questions grounded strictly in the personal social archive data</p>
          </div>
          
          {/* Platform Filtering badge */}
          <div className="chat-filters">
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, marginRight: '4px' }}>Filter:</span>
            <span className={`filter-badge ${filterPlatform === 'all' ? 'active' : ''}`} onClick={() => setFilterPlatform('all')}>All</span>
            <span className={`filter-badge ${filterPlatform === 'linkedin' ? 'active' : ''}`} onClick={() => setFilterPlatform('linkedin')}>LinkedIn</span>
            <span className={`filter-badge ${filterPlatform === 'twitter' ? 'active' : ''}`} onClick={() => setFilterPlatform('twitter')}>Twitter</span>
            <span className={`filter-badge ${filterPlatform === 'instagram' ? 'active' : ''}`} onClick={() => setFilterPlatform('instagram')}>Instagram</span>
          </div>
        </header>

        {messages.length === 0 ? (
          <div className="welcome-screen">
            <div className="welcome-icon">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            </div>
            <h1 className="welcome-title">Ask the Social Archive</h1>
            <p className="welcome-desc">
              Upload a social media data export on the left to build a semantic knowledge base. Once loaded, you can ask questions about remote work, tech opinions, coding, or lifestyle.
            </p>
            {stats.total_chunks > 0 ? (
              <div className="suggestions-grid">
                <button className="suggestion-card" onClick={() => triggerSuggestionClick("What does this person think about remote work?")}>
                  "What does this person think about remote work?"
                </button>
                <button className="suggestion-card" onClick={() => triggerSuggestionClick("Summarize this person's career focus based on their profile and posts.")}>
                  "Summarize this person's career focus..."
                </button>
                <button className="suggestion-card" onClick={() => triggerSuggestionClick("What technical topics or coding tools does this person write about?")}>
                  "What technical topics or coding tools..."
                </button>
                <button className="suggestion-card" onClick={() => triggerSuggestionClick("What are the core professional interests of this user?")}>
                  "What are the core professional interests..."
                </button>
              </div>
            ) : (
              <div style={{ padding: '12px 20px', borderRadius: 'var(--radius-sm)', border: '1px dashed var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '10px' }}>
                👈 Please upload an archive export to get started!
              </div>
            )}
          </div>
        ) : (
          <div className="chat-messages">
            {messages.map((msg) => (
              <div key={msg.id} className={`message ${msg.role}`}>
                <div className="avatar">
                  {msg.role === 'user' ? 'U' : 'AI'}
                </div>
                <div className="message-content">
                  <div className="message-bubble" style={{ whiteSpace: 'pre-wrap' }}>
                    {msg.content}
                    {msg.loading && <div className="spinner" style={{ marginTop: '8px' }}></div>}
                  </div>

                  {/* Render citations list for assistant answers */}
                  {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                    <div className="citations-container">
                      <div className="citations-header" onClick={() => toggleCitations(msg.id)}>
                        <span>Retrieved Sources ({msg.citations.length})</span>
                        <svg 
                          width="12" 
                          height="12" 
                          viewBox="0 0 24 24" 
                          fill="none" 
                          stroke="currentColor" 
                          strokeWidth="2.5" 
                          style={{ transform: openCitations[msg.id] ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}
                        >
                          <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                      </div>
                      
                      {openCitations[msg.id] && (
                        <div className="citations-list">
                          {msg.citations.map((cit) => (
                            <div key={cit.index} className="citation-card">
                              <div className="citation-card-header">
                                <span className={`citation-plat ${cit.platform.toLowerCase()}`}>
                                  [{cit.index}] {cit.platform.toUpperCase()}
                                </span>
                                <span className="citation-date">
                                  {cit.timestamp ? cit.timestamp.split("T")[0] : 'No Date'}
                                </span>
                              </div>
                              <div className="citation-text">
                                "{cit.snippet}"
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={chatBottomRef} />
          </div>
        )}

        {/* Chat input box */}
        <div className="chat-input-container">
          <form onSubmit={handleChatSubmit} className="chat-input-wrapper">
            <textarea
              className="chat-input"
              rows={1}
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              placeholder={stats.total_chunks > 0 ? "Ask anything about the ingested data..." : "Ingest data to start chatting..."}
              disabled={stats.total_chunks === 0 || chatLoading}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleChatSubmit(e);
                }
              }}
            />
            <button 
              type="submit" 
              className="btn btn-primary" 
              style={{ borderRadius: '50%', width: '40px', height: '40px', padding: 0 }}
              disabled={stats.total_chunks === 0 || !inputValue.trim() || chatLoading}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
