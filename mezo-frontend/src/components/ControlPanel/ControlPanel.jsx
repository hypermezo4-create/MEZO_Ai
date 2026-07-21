import React from 'react';
import './ControlPanel.css';
import { Cpu, HardDrive, Zap, Activity, ShieldCheck, Layers } from 'lucide-react';

export default function ControlPanel() {
  const stats = [
    { label: 'حالة محرك AI Engine', value: 'نشط (Active)', icon: Cpu, color: 'var(--accent-emerald)' },
    { label: 'استخدام الذاكرة (RAM)', value: '4.2 / 16 GB', icon: HardDrive, color: 'var(--accent-cyan)' },
    { label: 'السرعة / Latency', value: '18 ms', icon: Zap, color: 'var(--accent-amber)' },
    { label: 'المهارات المفعلة', value: '81 skill', icon: Layers, color: 'var(--accent-secondary)' },
    { label: 'حالة الأمان والـ RBAC', value: 'محمي (Secured)', icon: ShieldCheck, color: 'var(--accent-emerald)' },
    { label: 'أنشطة النظام الحية', value: '10 services', icon: Activity, color: 'var(--accent-primary)' }
  ];

  return (
    <div style={{ padding: '8px' }}>
      <h2 style={{ marginBottom: '16px', fontWeight: '700' }}>لوحة التحكم والسيطرة (MEZO Control Plane)</h2>
      <div className="control-panel-grid">
        {stats.map((item, i) => {
          const IconComponent = item.icon;
          return (
            <div key={i} className="glass-card stat-card">
              <div className="stat-icon" style={{ color: item.color, backgroundColor: `rgba(255,255,255,0.05)` }}>
                <IconComponent size={24} />
              </div>
              <div className="stat-info">
                <h4>{item.label}</h4>
                <div className="stat-value">{item.value}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
