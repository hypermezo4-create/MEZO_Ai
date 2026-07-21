import React, { useState, useRef, useEffect } from 'react';
import './ChatInterface.css';
import { Send, Bot, User, Cpu, Sparkles, Terminal } from 'lucide-react';

export default function ChatInterface() {
  const [messages, setMessages] = useState([
    {
      id: '1',
      sender: 'assistant',
      text: 'مرحباً بك في منصة MEZO Local AI! أنا جاهز لمساعدتك في إنشاء الأكواد، الإدارة، التحليل، والتدريب الذاتي. كيف يمكنني مساعدتك اليوم؟',
      timestamp: new Date()
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg = {
      id: Date.now().toString(),
      sender: 'user',
      text: input,
      timestamp: new Date()
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    // Simulate AI response stream
    setTimeout(() => {
      const botMsg = {
        id: (Date.now() + 1).toString(),
        sender: 'assistant',
        text: `تم استلام طلبك: "${userMsg.text}". قام محرك MEZO AI بالمعالجة بنجاح وتنفيذ الأمر عبر وكيل التحكم.`,
        timestamp: new Date()
      };
      setMessages((prev) => [...prev, botMsg]);
      setLoading(false);
    }, 1000);
  };

  return (
    <div className="glass-card chat-container">
      <div className="chat-messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message-bubble ${msg.sender}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px', opacity: 0.8, fontSize: '0.8rem' }}>
              {msg.sender === 'assistant' ? <Bot size={14} /> : <User size={14} />}
              <span>{msg.sender === 'assistant' ? 'MEZO Engine' : 'المستخدم'}</span>
            </div>
            <div>{msg.text}</div>
          </div>
        ))}
        {loading && (
          <div className="message-bubble assistant">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Cpu size={16} className="animate-spin" />
              <span>جاري التفكير والتوليد عبر محرك MEZO...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-area" onSubmit={handleSend}>
        <input
          type="text"
          className="chat-input"
          placeholder="اكتب رسالتك أو أمرك هنا..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" className="btn-primary" disabled={loading}>
          <Send size={18} />
          <span>إرسال</span>
        </button>
      </form>
    </div>
  );
}
