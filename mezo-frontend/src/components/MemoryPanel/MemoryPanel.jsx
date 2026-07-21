import React, { useState, useEffect, useCallback } from 'react';
import './MemoryPanel.css';

const CATEGORY_LABELS = {
  workflow:        '🔧 سير العمل',
  preference:      '⚙️ تفضيلات',
  project_context: '📁 سياق المشروع',
  sensitive:       '🔒 بيانات حساسة',
};

const CATEGORY_COLORS = {
  workflow:        'var(--accent-cyan, #22d3ee)',
  preference:      'var(--accent-purple, #a78bfa)',
  project_context: 'var(--accent-blue, #60a5fa)',
  sensitive:       '#f87171',
};

/**
 * MemoryPanel — user-facing view, edit, and delete interface for MEZO AI's
 * learned working-pattern memory.
 *
 * Shipped in the SAME component as the learning logic per spec requirement.
 * Connected to:
 *   GET    /api/user/memory        → list facts
 *   DELETE /api/user/memory/:id    → delete one fact
 *   DELETE /api/user/memory        → wipe all
 */
export default function MemoryPanel() {
  const [facts, setFacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showSensitive, setShowSensitive] = useState(false);
  const [wipePending, setWipePending] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const [filter, setFilter] = useState('all');

  const loadFacts = useCallback(async () => {
    setLoading(true);
    try {
      const url = showSensitive
        ? '/api/user/memory?include_sensitive=true'
        : '/api/user/memory';
      const res = await fetch(url);
      const data = await res.json();
      setFacts(data.facts || []);
    } catch {
      setFacts([]);
    } finally {
      setLoading(false);
    }
  }, [showSensitive]);

  useEffect(() => {
    loadFacts();
  }, [loadFacts]);

  const deleteFact = async (factId) => {
    try {
      await fetch(`/api/user/memory/${factId}`, { method: 'DELETE' });
      setFacts(prev => prev.filter(f => f.id !== factId));
      flash('تم حذف الحقيقة بنجاح');
    } catch {
      flash('فشل الحذف — حاول مجددًا', true);
    }
  };

  const wipeAll = async () => {
    if (!wipePending) {
      setWipePending(true);
      flash('اضغط مرة أخرى لتأكيد مسح كل الذاكرة');
      return;
    }
    try {
      await fetch('/api/user/memory', { method: 'DELETE' });
      setFacts([]);
      setWipePending(false);
      flash('تم مسح ذاكرة MEZO AI بالكامل');
    } catch {
      setWipePending(false);
      flash('فشل المسح — حاول مجددًا', true);
    }
  };

  const flash = (msg, isError = false) => {
    setStatusMsg({ text: msg, isError });
    setTimeout(() => setStatusMsg(''), 3500);
  };

  const displayedFacts = filter === 'all'
    ? facts
    : facts.filter(f => f.category === filter);

  const categories = ['all', ...new Set(facts.map(f => f.category))];

  return (
    <div className="memory-panel glass-card">
      <div className="memory-header">
        <div>
          <h3 className="memory-title">🧠 ذاكرة MEZO AI</h3>
          <p className="memory-subtitle">
            ما تعلّمه MEZO AI عن طريقة عملك — يمكنك عرضه وتعديله وحذفه في أي وقت.
          </p>
        </div>
        <div className="memory-count-badge">{facts.length} حقيقة</div>
      </div>

      {/* Controls */}
      <div className="memory-controls">
        <div className="memory-filter-row">
          {categories.map(cat => (
            <button
              key={cat}
              className={`filter-chip ${filter === cat ? 'filter-chip--active' : ''}`}
              onClick={() => setFilter(cat)}
              style={filter === cat && cat !== 'all' ? { borderColor: CATEGORY_COLORS[cat] } : {}}
            >
              {cat === 'all' ? '🗂️ الكل' : CATEGORY_LABELS[cat] || cat}
            </button>
          ))}
        </div>

        <div className="memory-toggle-row">
          <label className="sensitive-toggle">
            <input
              type="checkbox"
              checked={showSensitive}
              onChange={e => setShowSensitive(e.target.checked)}
            />
            <span>عرض البيانات الحساسة</span>
          </label>
        </div>
      </div>

      {/* Status flash */}
      {statusMsg && (
        <div className={`memory-status ${statusMsg.isError ? 'memory-status--error' : 'memory-status--ok'}`}>
          {statusMsg.text}
        </div>
      )}

      {/* Facts list */}
      {loading ? (
        <div className="memory-loading">جارٍ التحميل...</div>
      ) : displayedFacts.length === 0 ? (
        <div className="memory-empty">
          لا توجد حقائق مخزّنة في هذه الفئة بعد.
          <br />
          <span className="memory-empty-hint">
            سيبدأ MEZO AI بالتعلم من تفاعلاتك تلقائيًا.
          </span>
        </div>
      ) : (
        <ul className="memory-fact-list">
          {displayedFacts.map(fact => (
            <li key={fact.id} className="memory-fact-item">
              <div className="fact-left">
                <span
                  className="fact-category-badge"
                  style={{ borderColor: CATEGORY_COLORS[fact.category] || '#64748b', color: CATEGORY_COLORS[fact.category] || '#94a3b8' }}
                >
                  {CATEGORY_LABELS[fact.category] || fact.category}
                </span>
                <span className="fact-content">{fact.content}</span>
              </div>
              <div className="fact-right">
                <span className="fact-date">
                  {new Date(fact.created_at).toLocaleDateString('ar-EG', { month: 'short', day: 'numeric' })}
                </span>
                <button
                  className="fact-delete-btn"
                  onClick={() => deleteFact(fact.id)}
                  aria-label="حذف هذه الحقيقة"
                  title="حذف"
                >
                  ✕
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Wipe button */}
      <div className="memory-footer">
        <button
          id="wipe-memory-btn"
          className={`btn-wipe ${wipePending ? 'btn-wipe--confirm' : ''}`}
          onClick={wipeAll}
          disabled={facts.length === 0}
        >
          {wipePending ? '⚠️ اضغط مجددًا لتأكيد المسح الكامل' : '🗑️ مسح كل الذاكرة'}
        </button>
        <button className="btn-refresh" onClick={loadFacts}>↻ تحديث</button>
      </div>
    </div>
  );
}
