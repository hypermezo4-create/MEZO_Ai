import React, { useState } from 'react';
import './App.css';
import Dashboard from './pages/Dashboard/Dashboard';
import ChatPage from './pages/Chat/ChatPage';
import SkillsPage from './pages/Skills/SkillsPage';
import AdminPage from './pages/Admin/AdminPage';
import { LayoutDashboard, MessageSquare, Layers, Shield, Sparkles } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard />;
      case 'chat':
        return <ChatPage />;
      case 'skills':
        return <SkillsPage />;
      case 'admin':
        return <AdminPage />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="app-layout">
      <div className="sidebar">
        <div className="brand-header">
          <div className="brand-logo">M</div>
          <div>
            <div className="brand-title">MEZO AI</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Local AI Platform</div>
          </div>
        </div>

        <nav className="nav-menu">
          <div 
            className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            <LayoutDashboard size={20} />
            <span>لوحة التحكم</span>
          </div>

          <div 
            className={`nav-item ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <MessageSquare size={20} />
            <span>المحادثة المباشرة</span>
          </div>

          <div 
            className={`nav-item ${activeTab === 'skills' ? 'active' : ''}`}
            onClick={() => setActiveTab('skills')}
          >
            <Layers size={20} />
            <span>مدير المهارات</span>
          </div>

          <div 
            className={`nav-item ${activeTab === 'admin' ? 'active' : ''}`}
            onClick={() => setActiveTab('admin')}
          >
            <Shield size={20} />
            <span>الإدارة والأمان</span>
          </div>
        </nav>
      </div>

      <main className="main-content">
        {renderContent()}
      </main>
    </div>
  );
}
