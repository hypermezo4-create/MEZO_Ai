import React from 'react';
import './TrainingDashboard.css';
import { Play, RotateCcw, BrainCircuit, BarChart2 } from 'lucide-react';

export default function TrainingDashboard() {
  return (
    <div className="glass-card training-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3>لوحة نظام التدريب الذاتي (MEZO Self-Training)</h3>
        <button className="btn-primary">
          <Play size={16} />
          <span>بدء دورة تدريب جديدة</span>
        </button>
      </div>

      <div className="metrics-box">
        <div className="metric-pill">
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>عدد المحادثات المجمعة</div>
          <div style={{ fontSize: '1.4rem', fontWeight: '700', marginTop: '4px' }}>14,250</div>
        </div>
        <div className="metric-pill">
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>معدل دقة النموذج (Accuracy)</div>
          <div style={{ fontSize: '1.4rem', fontWeight: '700', marginTop: '4px', color: 'var(--accent-emerald)' }}>96.8%</div>
        </div>
        <div className="metric-pill">
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Loss Rate</div>
          <div style={{ fontSize: '1.4rem', fontWeight: '700', marginTop: '4px', color: 'var(--accent-cyan)' }}>0.042</div>
        </div>
      </div>
    </div>
  );
}
