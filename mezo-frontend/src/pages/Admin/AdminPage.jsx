import React from 'react';
import Settings from '../../components/Settings/Settings';
import FileManager from '../../components/FileManager/FileManager';

export default function AdminPage() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <h2>صفحة الإدارة المركزية والأمان (MEZO Admin)</h2>
      <Settings />
      <FileManager />
    </div>
  );
}
