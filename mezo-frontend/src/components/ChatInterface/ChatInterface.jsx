import React, { useState, useRef, useEffect } from 'react';
import './ChatInterface.css';
import ArtifactPanel from '../ArtifactPanel/ArtifactPanel';
import { Send, Bot, User, Cpu, Sparkles, AlertTriangle, FileCode } from 'lucide-react';

export default function ChatInterface() {
  const [messages, setMessages] = useState([
    {
      id: '1',
      sender: 'assistant',
      text: 'مرحباً بك في منصة MEZO Local AI! أنا جاهز لمساعدتك بكامل قدرات الذكاء الاصطناعي المحلي والسحابي. كيف يمكنني مساعدتك اليوم؟',
      timestamp: new Date()
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [liveStatus, setLiveStatus] = useState('جاهز ومستعد');
  const [activeArtifact, setActiveArtifact] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Helper to extract artifact content (>20 lines or code block)
  const extractArtifact = (text) => {
    const codeBlockMatch = text.match(/```(?:\w+)?\n([\s\S]*?)```/);
    if (codeBlockMatch) {
      return {
        filename: 'artifact_code.py',
        content: codeBlockMatch[1]
      };
    }
    const lines = text.split('\n');
    if (lines.length > 20) {
      return {
        filename: 'artifact_document.md',
        content: text
      };
    }
    return null;
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    setErrorMessage(null);
    const userText = input;
    setInput('');

    const userMsg = {
      id: Date.now().toString(),
      sender: 'user',
      text: userText,
      timestamp: new Date()
    };

    const botMsgId = (Date.now() + 1).toString();
    const initialBotMsg = {
      id: botMsgId,
      sender: 'assistant',
      text: '',
      timestamp: new Date()
    };

    setMessages((prev) => [...prev, userMsg, initialBotMsg]);
    setLoading(true);
    setLiveStatus('جاري تحديد الموفر وتوجيه الطلب...');

    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: userText, preferred_provider: 'auto', stream: true })
      });

      if (!response.ok) {
        if (response.status === 429) {
          throw new Error('Gemini quota exceeded — יرجى إعادة المحاولة أو التحويل للمحرك المحلي.');
        }
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || 'خطأ في الاتصال بمحرك MEZO.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulatedText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunkStr = decoder.decode(value, { stream: true });
        const lines = chunkStr.split('\n\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {

            const jsonStr = line.replace('data: ', '').trim();
            if (!jsonStr) continue;
            try {
              const eventData = JSON.parse(jsonStr);

              if (eventData.event === 'meta') {
                const provName = eventData.provider === 'local' ? 'المحرك المحلي' : 'Gemini Cloud';
                setLiveStatus(`متصل عبر ${provName} (${eventData.reason})`);
              } else if (eventData.event === 'token') {
                const tokenText = eventData.chunk?.text || '';
                accumulatedText += tokenText;
                
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === botMsgId ? { ...msg, text: accumulatedText } : msg
                  )
                );

                // Auto-detect artifact
                const detected = extractArtifact(accumulatedText);
                if (detected) {
                  setActiveArtifact(detected);
                }
              }
            } catch (err) {
              // Ignore partial chunk parsing
            }
          }
        }
      }
    } catch (err) {
      setErrorMessage(err.message || 'حدث خطأ غير متوقع أثناء معالجة الطلب.');
      setMessages((prev) => prev.filter((msg) => msg.id !== botMsgId));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-layout-wrapper">
      <div className="glass-card chat-container">
        <div className="provider-status-badge">
          <div className="status-dot" style={{ backgroundColor: loading ? 'var(--accent-amber)' : 'var(--accent-emerald)' }} />
          <span style={{ fontWeight: '600', color: 'var(--text-secondary)' }}>حالة الاتصال:</span>
          <span style={{ color: 'var(--text-primary)' }}>{liveStatus}</span>
        </div>

        {errorMessage && (
          <div className="error-banner">
            <AlertTriangle size={18} />
            <span>{errorMessage}</span>
          </div>
        )}

        <div className="chat-messages">
          {messages.map((msg) => {
            const artifact = msg.sender === 'assistant' ? extractArtifact(msg.text) : null;
            return (
              <div key={msg.id} className={`message-bubble ${msg.sender}`}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px', opacity: 0.8, fontSize: '0.8rem' }}>
                  {msg.sender === 'assistant' ? <Bot size={14} /> : <User size={14} />}
                  <span>{msg.sender === 'assistant' ? 'MEZO Engine' : 'المستخدم'}</span>
                </div>
                <div>{msg.text || (loading && msg.id === messages[messages.length - 1]?.id ? '...' : '')}</div>
                {artifact && (
                  <button className="artifact-trigger-btn" onClick={() => setActiveArtifact(artifact)}>
                    <FileCode size={16} />
                    <span>عرض الكود/المستند في لوحة الملحقات (Artifact)</span>
                  </button>
                )}
              </div>
            );
          })}
          {loading && !messages[messages.length - 1]?.text && (
            <div className="message-bubble assistant">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Cpu size={16} className="animate-spin" />
                <span>{liveStatus}...</span>
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

      {activeArtifact && (
        <ArtifactPanel
          artifact={activeArtifact}
          onClose={() => setActiveArtifact(null)}
        />
      )}
    </div>
  );
}
