import React, { useState, useEffect } from 'react';
import './Settings.css';
import { Save, Cpu, Cloud, Sparkles, CheckCircle2 } from 'lucide-react';

export default function Settings() {
  const [provider, setProvider] = useState('auto');
  const [capabilities, setCapabilities] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch('/api/providers/capabilities')
      .then((res) => res.json())
      .then((data) => setCapabilities(data))
      .catch(() => {});
  }, []);

  const handleSave = () => {
    localStorage.setItem('mezo_preferred_provider', provider);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="glass-card settings-form">
      <h3>إعدادات وتفضيلات مزود الذكاء الاصطناعي (AI Provider Settings)</h3>

      <div className="setting-row">
        <label>اختيار مزود الخدمة (AI Provider)</label>
        <select className="setting-input" value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="auto">تلقائي (Auto: Local First -> Gemini Cloud Fallback)</option>
          <option value="local">المحرك المحلي فقط (Local Engine - Ollama)</option>
          <option value="gemini">السحابة فقط (Gemini Cloud API)</option>
        </select>
      </div>

      {capabilities && (
        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-glass)', marginTop: '8px' }}>
          <h4 style={{ fontSize: '0.9rem', marginBottom: '10px', color: 'var(--accent-cyan)' }}>قدرات المزودين المتاحة (Resolved Provider Capabilities):</h4>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '0.85rem' }}>
            <div>
              <strong>🏠 المحرك المحلي (Local):</strong>
              <div>• النمط: {capabilities.local?.supports_streaming ? 'بث حي (Streaming)' : 'عادي'}</div>
              <div>• دعم الأدوات: {capabilities.local?.supports_tools ? 'مفعل' : 'غير مفعل'}</div>
              <div>• سياق الذاكرة: {capabilities.local?.max_context_tokens} tokens</div>
            </div>
            <div>
              <strong>☁️ Gemini Cloud:</strong>
              <div>• النمط: {capabilities.gemini?.supports_streaming ? 'بث حي (Streaming)' : 'عادي'}</div>
              <div>• دعم الأدوات: {capabilities.gemini?.supports_tools ? 'مفعل' : 'غير مفعل'}</div>
              <div>• سياق الذاكرة: {capabilities.gemini?.max_context_tokens} tokens</div>
            </div>
          </div>
        </div>
      )}

      <button className="btn-primary" style={{ alignSelf: 'flex-start', marginTop: '12px' }} onClick={handleSave}>
        {saved ? <CheckCircle2 size={16} /> : <Save size={16} />}
        <span>{saved ? 'تم حفظ التفضيلات' : 'حفظ الإعدادات'}</span>
      </button>
    </div>
  );
}
