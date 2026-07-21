import React, { useState } from 'react';
import './Settings.css';
import { Save, Key, Globe, Moon } from 'lucide-react';

export default function Settings() {
  const [model, setModel] = useState('MEZO-Custom-v1');
  const [lang, setLang] = useState('ar');

  return (
    <div className="glass-card settings-form">
      <h3>إعدادات منصة MEZO</h3>
      
      <div className="setting-row">
        <label>نموذج الذكاء الاصطناعي الافتراضي</label>
        <select className="setting-input" value={model} onChange={(e) => setModel(e.target.value)}>
          <option value="MEZO-Custom-v1">MEZO Custom Local Model v1</option>
          <option value="MEZO-FineTuned-Llama3">MEZO Fine-Tuned Llama 3</option>
          <option value="MEZO-CodeGenerator">MEZO Code Generator Engine</option>
        </select>
      </div>

      <div className="setting-row">
        <label>لغة الواجهة</label>
        <select className="setting-input" value={lang} onChange={(e) => setLang(e.target.value)}>
          <option value="ar">العربية (Arabic)</option>
          <option value="en">English</option>
        </select>
      </div>

      <button className="btn-primary" style={{ alignSelf: 'flex-start', marginTop: '12px' }}>
        <Save size={16} />
        <span>حفظ الإعدادات</span>
      </button>
    </div>
  );
}
