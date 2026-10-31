import React, { useState, useEffect } from 'react';
import { Brain, Trash2, Plus, Zap, X } from 'lucide-react';
import {
  fetchMemories,
  storeMemory,
  searchMemories,
  deleteMemory,
  wipeAllMemories,
  type MemoryItemDto,
  type MemorySearchResultDto,
} from '../services/api';

export const SemanticMemory: React.FC = () => {
  const [memories, setMemories] = useState<MemoryItemDto[]>([]);
  const [searchResults, setSearchResults] = useState<MemorySearchResultDto[] | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // New Memory Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newCategory, setNewCategory] = useState('preference');
  const [newConfidence, setNewConfidence] = useState(1.0);

  useEffect(() => {
    loadMemories();
  }, [selectedCategory]);

  const showNotification = (type: 'success' | 'error', text: string) => {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4500);
  };

  const loadMemories = async () => {
    setLoading(true);
    try {
      const cat = selectedCategory === 'all' ? undefined : selectedCategory;
      const data = await fetchMemories(cat);
      setMemories(data);
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to load memories');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }

    setSearchLoading(true);
    try {
      const cat = selectedCategory === 'all' ? undefined : selectedCategory;
      const results = await searchMemories(searchQuery, 6, 0.05, cat);
      setSearchResults(results);
    } catch (err: any) {
      showNotification('error', err.message || 'Vector search failed');
    } finally {
      setSearchLoading(false);
    }
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    setSearchResults(null);
  };

  const handleAddMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) {
      showNotification('error', 'Content is required.');
      return;
    }

    try {
      const created = await storeMemory({
        content: newContent,
        category: newCategory,
        confidence: newConfidence,
        source: 'manual',
      });
      showNotification('success', `Stored ${created.category} memory item.`);
      setShowAddModal(false);
      setNewContent('');
      await loadMemories();
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to save memory');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMemory(id);
      showNotification('success', 'Memory record deleted.');
      setMemories(memories.filter((m) => m.id !== id));
      if (searchResults) {
        setSearchResults(searchResults.filter((s) => s.id !== id));
      }
    } catch (err: any) {
      showNotification('error', err.message || 'Failed to delete');
    }
  };

  const handleWipeAll = async () => {
    const confirmed = window.confirm(
      'PRIVACY & POLICY GATE CONFIRMATION\n\nAre you sure you want to permanently erase ALL stored semantic memories and learned preferences from the database?'
    );
    if (!confirmed) return;

    try {
      const res = await wipeAllMemories(true);
      showNotification('success', res.message || 'All memories wiped.');
      setMemories([]);
      setSearchResults(null);
    } catch (err: any) {
      showNotification('error', err.message || 'Wipe rejected');
    }
  };

  const getCategoryColor = (cat: string) => {
    switch (cat) {
      case 'preference':
        return 'bg-purple-500/10 text-purple-400 border-purple-500/30';
      case 'fact':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/30';
      case 'goal':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header and Control Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-violet-500/10 border border-violet-500/30 flex items-center justify-center text-violet-400 font-bold">
              <Brain className="w-5 h-5 text-violet-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
                Semantic Memory & Vector Search
                <span className="text-xs bg-violet-500/20 text-violet-400 border border-violet-500/30 px-2 py-0.5 rounded-full font-mono">
                  Phase 8
                </span>
              </h2>
              <p className="text-sm text-slate-400">
                1536-dimensional embedding storage with cosine similarity search and GDPR privacy controls.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleWipeAll}
            className="px-3.5 py-2 bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 border border-rose-800/60 rounded-xl text-xs font-semibold transition flex items-center gap-1.5"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Wipe Memory (GDPR)</span>
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-xs font-bold transition shadow-md flex items-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Store Context</span>
          </button>
        </div>
      </div>

      {notification && (
        <div
          className={`p-4 rounded-xl text-sm border flex items-center justify-between ${
            notification.type === 'success'
              ? 'bg-emerald-950/60 border-emerald-800 text-emerald-300'
              : 'bg-rose-950/60 border-rose-800 text-rose-300'
          }`}
        >
          <span>{notification.text}</span>
          <button onClick={() => setNotification(null)} className="text-xs hover:underline ml-4">
            Dismiss
          </button>
        </div>
      )}

      {/* Semantic Search Box */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <Zap className="w-4 h-4 text-violet-400" /> Vector Similarity Query Engine
            </h3>
            <p className="text-xs text-slate-400">
              Query your knowledge base with natural language. Vector embeddings rank results by cosine distance.
            </p>
          </div>
          {searchResults && (
            <button
              onClick={handleClearSearch}
              className="text-xs text-slate-400 hover:text-white px-2.5 py-1 rounded bg-slate-800"
            >
              Clear Search
            </button>
          )}
        </div>

        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            placeholder="Ask anything (e.g. 'What are my favorite technologies?' or 'What is my schedule preference?')..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 bg-slate-800/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-500"
          />
          <button
            type="submit"
            disabled={searchLoading}
            className="px-5 py-2.5 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-sm font-bold transition shadow-md disabled:opacity-50"
          >
            {searchLoading ? 'Searching...' : 'Vector Search'}
          </button>
        </form>

        {/* Search Results Display */}
        {searchResults && (
          <div className="space-y-3 pt-2">
            <div className="text-xs font-semibold text-slate-400 flex items-center justify-between">
              <span>Ranked Vector Search Results ({searchResults.length})</span>
              <span className="text-[11px] font-mono text-violet-400">Model: 1536-dim Embedding</span>
            </div>

            {searchResults.length === 0 ? (
              <div className="text-xs text-slate-500 py-6 text-center bg-slate-950/40 rounded-xl border border-slate-800">
                No memories met the similarity threshold.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {searchResults.map((res) => {
                  const pct = Math.max(0, Math.min(100, Math.round(res.similarity * 100)));
                  return (
                    <div
                      key={res.id}
                      className="p-4 rounded-xl bg-slate-950/70 border border-violet-900/40 flex flex-col justify-between space-y-2"
                    >
                      <div>
                        <div className="flex items-center justify-between mb-1.5">
                          <span
                            className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${getCategoryColor(
                              res.category
                            )}`}
                          >
                            {res.category}
                          </span>
                          <span className="text-xs font-mono font-bold text-violet-300">
                            {pct}% Match
                          </span>
                        </div>
                        <p className="text-xs text-slate-200 leading-relaxed font-sans">{res.content}</p>
                      </div>

                      {/* Cosine Similarity Bar */}
                      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-gradient-to-r from-violet-500 to-indigo-400 h-1.5 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Category Filter Chips & Memory Store Grid */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              Contextual Knowledge Base
              <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full font-mono border border-slate-700">
                {memories.length}
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              User facts, developer preferences, and goals saved across conversational sessions.
            </p>
          </div>

          {/* Filter Pills */}
          <div className="flex gap-1.5 overflow-x-auto">
            {['all', 'preference', 'fact', 'goal'].map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-3 py-1 rounded-xl text-xs font-medium capitalize transition ${
                  selectedCategory === cat
                    ? 'bg-violet-600 text-white font-bold'
                    : 'bg-slate-800/80 text-slate-400 hover:text-slate-200'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="text-center py-16 text-slate-500 text-sm">Loading memories...</div>
        ) : memories.length === 0 ? (
          <div className="text-center py-16 text-slate-500 text-sm">
            No memories stored in this category yet. Click &quot;Store Context&quot; to teach the assistant.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {memories.map((mem) => (
              <div
                key={mem.id}
                className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 hover:border-violet-500/40 transition flex flex-col justify-between space-y-3"
              >
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span
                      className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${getCategoryColor(
                        mem.category
                      )}`}
                    >
                      {mem.category}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      Conf: {Math.round(mem.confidence * 100)}%
                    </span>
                  </div>
                  <p className="text-xs text-slate-200 leading-relaxed font-sans">{mem.content}</p>
                </div>

                <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-500">
                  <span className="font-mono">src: {mem.source}</span>
                  <button
                    onClick={() => handleDelete(mem.id)}
                    className="text-rose-400 hover:text-rose-300 transition text-[11px]"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add Memory Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-white">Teach Assistant New Context</h3>
                <p className="text-xs text-slate-400">
                  Generates a vector embedding and indexes into semantic memory.
                </p>
              </div>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddMemory} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Context / Fact / Preference</label>
                <textarea
                  rows={4}
                  placeholder="e.g. 'I prefer writing backend services in Python FastAPI, and always want concise unit tests.'"
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  required
                  className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Category</label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="w-full bg-slate-800/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-violet-500"
                  >
                    <option value="preference">Preference</option>
                    <option value="fact">Fact</option>
                    <option value="goal">Goal</option>
                    <option value="interaction">Interaction</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">
                    Confidence ({Math.round(newConfidence * 100)}%)
                  </label>
                  <input
                    type="range"
                    min="0.5"
                    max="1.0"
                    step="0.05"
                    value={newConfidence}
                    onChange={(e) => setNewConfidence(parseFloat(e.target.value))}
                    className="w-full mt-2"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-xs font-bold transition shadow-md"
                >
                  Store & Embed
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

