'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth-store';
import { buildCitationUrl, RAG_API } from '@/lib/api';
import type { Citation, Message } from '@/lib/types';

const PROMPTS = [
  'What financial aid is available?',
  'Summarize undergraduate admissions.',
  'What student policies are available?',
];

export default function ChatPage() {
  const { session, onSessionExpired } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [query, setQuery] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState('');
  const [citationError, setCitationError] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, chatLoading]);

  const openCitation = useCallback(async (source: string, download = false) => {
    if (!session) return;
    setCitationError('');
    const url = buildCitationUrl(source, RAG_API);
    if (!url) { setCitationError('Citation not available.'); return; }
    if (/^https?:\/\//i.test(url) && !url.includes(`${RAG_API}/files/`)) {
      window.open(url, '_blank', 'noopener,noreferrer');
      return;
    }
    try {
      const res = await fetch(download ? `${url}?download=true` : url, {
        headers: { Authorization: `Bearer ${session.accessToken}` },
      });
      if (res.status === 401) { onSessionExpired(); return; }
      if (!res.ok) throw new Error(`Unable to open citation (${res.status})`);
      const objectUrl = URL.createObjectURL(await res.blob());
      if (download) {
        const a = document.createElement('a');
        a.href = objectUrl;
        a.download = source.split('/').pop() || 'citation';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } else {
        window.open(objectUrl, '_blank', 'noopener,noreferrer');
      }
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1200);
    } catch (err) {
      setCitationError(err instanceof Error ? err.message : 'Unable to open citation.');
    }
  }, [session, onSessionExpired]);

  const sendChat = useCallback(async () => {
    if (!session || !query.trim() || chatLoading) return;
    const userText = query.trim();
    const ts = Date.now();
    setMessages(prev => [...prev,
      { role: 'user', text: userText, timestamp: ts },
      { role: 'bot', text: '', timestamp: ts + 1 },
    ]);
    setChatLoading(true);
    setChatError('');
    setQuery('');
    try {
      const res = await fetch(`${RAG_API}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.accessToken}`,
          'X-Tenant-ID': session.user.tenant_id,
        },
        body: JSON.stringify({ query: userText }),
      });
      if (res.status === 401) { onSessionExpired('Session expired during chat.'); return; }
      if (!res.ok || !res.body) throw new Error(`Chat failed (${res.status})`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let streamed = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';
        for (const frame of parts) {
          const line = frame.trim();
          if (!line.startsWith('data: ')) continue;
          const payload = JSON.parse(line.slice(6)) as {
            chunk: string; done: boolean; citations?: Citation[]; insufficient_evidence?: boolean;
          };
          if (!payload.done) {
            streamed += payload.chunk;
            setMessages(prev => prev.map(m => m.timestamp === ts + 1 ? { ...m, text: streamed } : m));
          } else {
            setMessages(prev => prev.map(m => m.timestamp === ts + 1
              ? { ...m, text: streamed, citations: payload.citations || [], insufficient_evidence: payload.insufficient_evidence || false }
              : m));
          }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Chat error';
      setChatError(msg);
      setMessages(prev => prev.map(m => m.timestamp === ts + 1 ? { ...m, text: `Error: ${msg}` } : m));
    } finally {
      setChatLoading(false);
    }
  }, [session, query, chatLoading, onSessionExpired]);

  return (
    <div className="content-panel">
      <div className="page-header">
        <h1>Chat</h1>
        <p>Ask questions against your knowledge base. Answers are grounded in citations.</p>
      </div>

      <div className="panel flex min-h-[620px] flex-col" id="chat-panel">
        {/* Prompt chips */}
        <div className="flex flex-wrap gap-2 mb-4">
          {PROMPTS.map(p => (
            <button key={p} className="prompt-chip" onClick={() => setQuery(p)}>{p}</button>
          ))}
        </div>

        {/* Messages */}
        <div className="chat-scroll flex-1" id="chat-scroll">
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon text-2xl">💬</div>
              <p className="text-base font-semibold text-slate-800 mt-2">Ask your first question</p>
              <p className="text-sm text-slate-500 mt-1 max-w-sm">
                Answers are grounded in your workspace's knowledge sources. Citations appear automatically.
              </p>
            </div>
          ) : messages.map(m => (
            <div key={`${m.timestamp}-${m.role}`} className={`message-row ${m.role === 'user' ? 'is-user' : ''}`}>
              <div className={`message-bubble ${m.role === 'user' ? 'user' : m.insufficient_evidence ? 'warning' : 'assistant'}`}>
                <p className="whitespace-pre-wrap">{m.text || (chatLoading && m.role === 'bot' ? '…' : '')}</p>
                {m.citations && m.citations.length > 0 && (
                  <div className="mt-4 space-y-2">
                    <p className="text-xs font-semibold uppercase text-slate-400">
                      Citations ({m.citations.length})
                    </p>
                    {m.citations.map(c => (
                      <div key={`${m.timestamp}-c-${c.id}`} className="citation-item">
                        <div className="font-semibold text-slate-800">[{c.id}] {c.title || 'Source'}</div>
                        <div className="mt-1 break-all text-slate-500">{c.source}</div>
                        <div className="mt-2 flex gap-2">
                          <button className="btn-small" onClick={() => void openCitation(c.source, false)}>Open</button>
                          <button className="btn-small" onClick={() => void openCitation(c.source, true)}>Download</button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Composer */}
        <div className="composer mt-4">
          <textarea
            className="field-input min-h-12 flex-1 resize-none"
            placeholder="Ask a question about your knowledge base… (Enter to send, Shift+Enter for new line)"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendChat(); }
            }}
          />
          <button
            className="btn-primary self-stretch px-6"
            disabled={chatLoading || !query.trim()}
            onClick={() => void sendChat()}
          >
            {chatLoading ? '…' : 'Send'}
          </button>
        </div>

        {chatError && <p className="status-error mt-3">{chatError}</p>}
        {citationError && <p className="status-error mt-2">{citationError}</p>}
      </div>
    </div>
  );
}
