import React from 'react';
import { Layers, Shield, Code, Cpu, CheckCircle } from 'lucide-react';

export default function SkillsPage() {
  const categories = [
    { title: 'مهارات النظام (System Skills)', count: 24, icon: Cpu },
    { title: 'مهارات التطوير (Development Skills)', count: 32, icon: Code },
    { title: 'مهارات التعلم الذاتي (Learning Skills)', count: 15, icon: Layers },
    { title: 'مهارات الحماية والحراس (Guard Skills)', count: 10, icon: Shield }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <h2 style={{ fontWeight: '700' }}>مكتبة مهارات MEZO (Skills Manager)</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
        {categories.map((cat, idx) => {
          const IconComp = cat.icon;
          return (
            <div key={idx} className="glass-card" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                <IconComp size={24} style={{ color: 'var(--accent-primary)' }} />
                <h4 style={{ fontSize: '1rem' }}>{cat.title}</h4>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>عدد المهارات</span>
                <span style={{ fontWeight: '700', color: 'var(--accent-emerald)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <CheckCircle size={14} /> {cat.count} مهارة مفعلة
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
