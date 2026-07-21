import React, { useState } from 'react';
import './ArtifactPanel.css';
import { Code, Copy, Download, Check, X } from 'lucide-react';

export default function ArtifactPanel({ artifact, onClose }) {
  const [copied, setCopied] = useState(false);

  if (!artifact) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(artifact.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([artifact.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = artifact.filename || 'mezo_artifact.txt';
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="artifact-panel glass-card">
      <div className="artifact-header">
        <div className="artifact-title">
          <Code size={18} />
          <span>{artifact.filename || 'عنصر ملحق / Artifact'}</span>
        </div>
        <div className="artifact-actions">
          <button className="btn-secondary" style={{ padding: '6px 12px' }} onClick={handleCopy}>
            {copied ? <Check size={14} style={{ color: 'var(--accent-emerald)' }} /> : <Copy size={14} />}
            <span style={{ fontSize: '0.8rem' }}>{copied ? 'تم النسخ' : 'نسخ'}</span>
          </button>
          <button className="btn-secondary" style={{ padding: '6px 12px' }} onClick={handleDownload}>
            <Download size={14} />
            <span style={{ fontSize: '0.8rem' }}>تحميل</span>
          </button>
          <button className="btn-secondary" style={{ padding: '6px 8px' }} onClick={onClose}>
            <X size={14} />
          </button>
        </div>
      </div>
      <div className="artifact-body">
        <code>{artifact.content}</code>
      </div>
    </div>
  );
}
