import React from 'react';
import './FileManager.css';
import { Folder, FileText, Code, Download, Trash2, Eye } from 'lucide-react';

export default function FileManager() {
  const dummyFiles = [
    { name: 'mezo-config.json', size: '2.4 KB', type: 'json' },
    { name: 'model_weights.bin', size: '1.2 GB', type: 'bin' },
    { name: 'training_dataset.jsonl', size: '45.8 MB', type: 'jsonl' },
    { name: 'agent_logs.log', size: '840 KB', type: 'log' },
  ];

  return (
    <div className="glass-card file-manager-container">
      <h3>مدير ملفات MEZO Workspace</h3>
      <div className="file-list">
        {dummyFiles.map((file, idx) => (
          <div key={idx} className="file-item">
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <FileText size={20} style={{ color: 'var(--accent-cyan)' }} />
              <div>
                <div style={{ fontWeight: '600' }}>{file.name}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{file.size}</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="btn-secondary" style={{ padding: '6px 10px' }}><Eye size={16} /></button>
              <button className="btn-secondary" style={{ padding: '6px 10px' }}><Download size={16} /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
