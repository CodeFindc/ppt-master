import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, 
  ChevronLeft, 
  ChevronRight, 
  Download, 
  MessageSquare, 
  Plus, 
  Trash2,
  Presentation,
  FileCheck
} from 'lucide-react';

interface ToolCall {
  name: string;
  args: any;
  id: string;
  status?: 'running' | 'success' | 'failed';
  result?: any;
}

interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  logLines?: string[];
  tool_calls?: ToolCall[];
  type?: 'HumanMessage' | 'AIMessage' | 'SystemMessage' | 'ToolMessage';
  name?: string;
  tool_call_id?: string;
  id?: string;
}

interface ChatSession {
  id: string;
  title: string;
  timestamp: number;
}

interface SlideInfo {
  name: string;
  annotated: boolean;
  annotation_count: number;
  ok: boolean;
  error?: string;
  mtime: number;
}

// Utility to set session cookie
const setSessionCookie = (sessionId: string) => {
  document.cookie = `session_id=${sessionId}; path=/; max-age=2592000; same-site=lax`;
};

// Utility to get session ID from URL path or Cookie
const getSessionIdFromUrl = (): string | null => {
  const path = window.location.pathname.substring(1);
  if (path && path.length > 10) {
    return path;
  }
  return null;
};

const renderStructuredLogs = (logLines: string[]) => {
  // Parse lines to build a list of steps
  const steps: { name: string, status: 'running' | 'success' | 'failed' | 'info', details?: string }[] = [];
  
  logLines.forEach(line => {
    if (line.includes('[TOOL CALL] Executing:')) {
      const match = line.match(/Executing:\s+(\w+)/);
      if (match) {
        steps.push({
          name: match[1],
          status: 'running'
        });
      }
    } else if (line.includes('[TOOL RESULT] Status:')) {
      const match = line.match(/Status:\s+(\w+)/);
      if (match && steps.length > 0) {
        const statusStr = match[1].toLowerCase();
        const lastStep = steps[steps.length - 1];
        lastStep.status = statusStr.includes('success') ? 'success' : 'failed';
      }
    } else if (line.includes('[TOOL ERROR] Exception raised:') || line.includes('Error:')) {
      if (steps.length > 0) {
        steps[steps.length - 1].status = 'failed';
      }
    } else if (line.includes('[Node Update] Completed execution node:')) {
      const match = line.match(/node:\s+(\w+)/);
      if (match) {
        steps.push({
          name: `Graph Node: ${match[1]}`,
          status: 'info'
        });
      }
    }
  });

  if (steps.length === 0) {
    return <pre className="logs-content">{logLines.join('\n')}</pre>;
  }

  return (
    <div className="log-steps-container" style={{ display: 'flex', flexDirection: 'column', gap: '8px', margin: '8px 0' }}>
      <div style={{ fontSize: '11px', fontWeight: 600, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Execution Pipeline
      </div>
      <div className="log-steps-list" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {steps.map((step, idx) => (
          <div key={idx} style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between',
            padding: '6px 10px', 
            background: '#f8fafc', 
            border: '1px solid #e2e8f0', 
            borderRadius: '6px',
            fontSize: '12.5px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: step.status === 'success' ? '#10b981' : 
                            step.status === 'failed' ? '#ef4444' : 
                            step.status === 'info' ? '#3b82f6' : '#f59e0b',
                display: 'inline-block'
              }} />
              <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#334155' }}>
                {step.name}
              </span>
            </div>
            <span style={{
              fontSize: '11px',
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: '4px',
              background: step.status === 'success' ? '#d1fae5' : 
                          step.status === 'failed' ? '#fee2e2' : 
                          step.status === 'info' ? '#dbeafe' : '#fef3c7',
              color: step.status === 'success' ? '#065f46' : 
                     step.status === 'failed' ? '#991b1b' : 
                     step.status === 'info' ? '#1e40af' : '#92400e',
              textTransform: 'uppercase'
            }}>
              {step.status === 'running' ? 'running...' : step.status}
            </span>
          </div>
        ))}
      </div>
      <details style={{ marginTop: '8px' }}>
        <summary style={{ fontSize: '11px', cursor: 'pointer', color: '#64748b', fontWeight: 500 }}>
          View Raw Console Output
        </summary>
        <pre className="logs-content" style={{ marginTop: '4px' }}>{logLines.join('\n')}</pre>
      </details>
    </div>
  );
};

const renderToolCalls = (toolCalls: ToolCall[], toolResultsMap: Map<string, Message>) => {
  return (
    <div className="tool-calls-pipeline" style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
      margin: '10px 0 4px 0',
      padding: '10px 12px',
      background: '#f8fafc',
      border: '1.5px dashed #cbd5e1',
      borderRadius: '8px',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        fontSize: '11px',
        fontWeight: 700,
        color: '#64748b',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        marginBottom: '2px'
      }}>
        <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', background: '#3b82f6' }} />
        Agent Execution Pipeline
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {toolCalls.map((tc, idx) => {
          const toolResult = toolResultsMap.get(tc.id);
          
          let status: 'running' | 'success' | 'failed' = 'running';
          let parsedResult: any = undefined;
          
          if (toolResult) {
            try {
              parsedResult = JSON.parse(toolResult.content);
            } catch (e) {
              parsedResult = { raw: toolResult.content };
            }
            if (parsedResult && (parsedResult.success === true || parsedResult.returncode === 0)) {
              status = 'success';
            } else {
              status = 'failed';
            }
          } else if (tc.status) {
            status = tc.status;
            parsedResult = tc.result;
          }
          
          const isSuccess = status === 'success';
          const isFailed = status === 'failed';
          const isRunning = status === 'running';
          
          let statusBg = '#fef3c7';
          let statusColor = '#92400e';
          if (isSuccess) {
            statusBg = '#d1fae5';
            statusColor = '#065f46';
          } else if (isFailed) {
            statusBg = '#fee2e2';
            statusColor = '#991b1b';
          } else if (isRunning) {
            statusBg = '#dbeafe';
            statusColor = '#1e40af';
          }
          
          return (
            <details 
              key={tc.id || idx} 
              style={{ 
                border: '1px solid #e2e8f0', 
                borderRadius: '6px', 
                background: '#ffffff',
                overflow: 'hidden'
              }}
            >
              <summary style={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'space-between',
                padding: '6px 10px', 
                cursor: 'pointer',
                userSelect: 'none',
                outline: 'none',
                listStyle: 'none'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: isSuccess ? '#10b981' : isFailed ? '#ef4444' : '#3b82f6',
                    display: 'inline-block'
                  }} />
                  <span style={{ fontFamily: 'monospace', fontWeight: 600, fontSize: '12.5px', color: '#334155' }}>
                    {tc.name}
                  </span>
                  <span style={{ fontSize: '10.5px', color: '#94a3b8' }}>
                    (click to expand)
                  </span>
                </div>
                <span style={{
                  fontSize: '9.5px',
                  fontWeight: 700,
                  padding: '2px 5px',
                  borderRadius: '4px',
                  background: statusBg,
                  color: statusColor,
                  textTransform: 'uppercase'
                }}>
                  {status}
                </span>
              </summary>
              
              <div style={{ 
                padding: '8px 10px', 
                borderTop: '1px solid #f1f5f9', 
                background: '#f8fafc',
                fontSize: '11px',
                fontFamily: 'monospace',
                display: 'flex',
                flexDirection: 'column',
                gap: '6px',
                overflowX: 'auto'
              }}>
                {tc.args && (
                  <div>
                    <div style={{ fontWeight: 600, color: '#64748b', marginBottom: '2px', fontSize: '10.5px' }}>Arguments:</div>
                    <pre style={{ margin: 0, padding: '4px 6px', background: '#f1f5f9', borderRadius: '4px', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                      {JSON.stringify(tc.args, null, 2)}
                    </pre>
                  </div>
                )}
                {parsedResult !== undefined && (
                  <div>
                    <div style={{ fontWeight: 600, color: '#64748b', marginBottom: '2px', fontSize: '10.5px' }}>Execution Output:</div>
                    <pre style={{ margin: 0, padding: '4px 6px', background: '#f1f5f9', borderRadius: '4px', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                      {JSON.stringify(parsedResult, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </details>
          );
        })}
      </div>
    </div>
  );
};;

const getSvgAspectRatio = (svgString: string): string => {
  if (!svgString) return '16 / 9';
  
  // Try to find viewBox attribute
  const viewBoxMatch = svgString.match(/viewBox=["']\s*([0-9.-]+)\s+([0-9.-]+)\s+([0-9.-]+)\s+([0-9.-]+)\s*["']/i);
  if (viewBoxMatch) {
    const w = parseFloat(viewBoxMatch[3]);
    const h = parseFloat(viewBoxMatch[4]);
    if (w > 0 && h > 0) {
      return `${w} / ${h}`;
    }
  }
  
  // Try to find width and height attributes
  const widthMatch = svgString.match(/width=["']\s*([0-9.-]+)(px)?\s*["']/i);
  const heightMatch = svgString.match(/height=["']\s*([0-9.-]+)(px)?\s*["']/i);
  if (widthMatch && heightMatch) {
    const w = parseFloat(widthMatch[1]);
    const h = parseFloat(heightMatch[1]);
    if (w > 0 && h > 0) {
      return `${w} / ${h}`;
    }
  }
  
  return '16 / 9';
};

export const App: React.FC = () => {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>('');
  
  // Chat States
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [agentRunning, setAgentRunning] = useState(false);
  const [activeLogs, setActiveLogs] = useState<string[]>([]);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [editorCollapsed, setEditorCollapsed] = useState(false);
  
  // Workspace / Slides States
  const [projectInitialized, setProjectInitialized] = useState(false);
  const [slides, setSlides] = useState<SlideInfo[]>([]);
  const [currentSlide, setCurrentSlide] = useState<string | null>(null);
  const [svgContent, setSvgContent] = useState<string>('');
  const [selectedElementId, setSelectedElementId] = useState<string | null>(null);
  const [selectedElementTag, setSelectedElementTag] = useState<string | null>(null);
  const [slideAnnotations, setSlideAnnotations] = useState<Record<string, string>>({});
  const [annotationInput, setAnnotationInput] = useState('');
  
  // Utility States
  const [initLoading, setInitLoading] = useState(false);
  const [statusText, setStatusText] = useState('Ready');
  const [annotationsDirty, setAnnotationsDirty] = useState(false);
  
  const chatMessagesEndRef = useRef<HTMLDivElement>(null);

  // 1. Initial Session Loading
  useEffect(() => {
    let currentId = getSessionIdFromUrl();
    if (!currentId) {
      const match = document.cookie.match(/(?:^|; )session_id=([^;]*)/);
      currentId = match ? match[1] : null;
    }
    
    if (!currentId) {
      currentId = crypto.randomUUID();
      window.history.replaceState(null, '', `/${currentId}`);
    } else {
      if (window.location.pathname !== `/${currentId}`) {
        window.history.replaceState(null, '', `/${currentId}`);
      }
    }
    
    setActiveSessionId(currentId);
    setSessionCookie(currentId);

    // Load Sessions list from localStorage
    const saved = localStorage.getItem('ppt_sessions');
    let loadedSessions: ChatSession[] = [];
    if (saved) {
      try {
        loadedSessions = JSON.parse(saved);
        setSessions(loadedSessions);
      } catch (e) {
        console.error('Error parsing sessions:', e);
      }
    }
    
    // Add current session if not already in list
    if (currentId && !loadedSessions.some(s => s.id === currentId)) {
      const newSess: ChatSession = {
        id: currentId,
        title: 'New Presentation Project',
        timestamp: Date.now()
      };
      const updated = [newSess, ...loadedSessions];
      setSessions(updated);
      localStorage.setItem('ppt_sessions', JSON.stringify(updated));
    }
  }, []);

  // 2. Load Chat History and Check project workspace on session switch
  useEffect(() => {
    if (!activeSessionId) return;

    setSessionCookie(activeSessionId);
    setSelectedElementId(null);
    setSelectedElementTag(null);
    setSvgContent('');
    setSlideAnnotations({});
    setAnnotationInput('');
    setAnnotationsDirty(false);
    
    // Fetch History
    fetch('/api/agent/history')
      .then(res => res.json())
      .then(data => {
        const msgs = data.messages || [];
        const hasRenderable = msgs.some((m: any) => m.role === 'user' || m.role === 'assistant');
        if (!hasRenderable) {
          setMessages([
            {
              role: 'assistant',
              content: 'Hello! I am your AI Presentation Assistant. I can help you generate presentation slide decks page-by-page. Describe the topic you want to write about to begin!'
            },
            ...msgs
          ]);
        } else {
          setMessages(msgs);
        }
      })
      .catch(err => {
        console.error('Failed to load chat history:', err);
      });

    // Check project workspace state
    checkAndLoadSlides(activeSessionId, true);
  }, [activeSessionId]);

  // 3. Scroll messages
  useEffect(() => {
    chatMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activeLogs, agentRunning]);

  // 4. Fetch slide content when selected slide changes
  useEffect(() => {
    if (!currentSlide) return;
    loadSlideContent(currentSlide);
  }, [currentSlide]);

  // Check slides list and auto-initialize if empty (brand new session)
  const checkAndLoadSlides = (sessionId: string, autoInitIfEmpty = false) => {
    fetch('/api/slides')
      .then(res => res.json())
      .then(data => {
        const list = data.slides || [];
        setSlides(list);
        const hasSlides = list.length > 0;
        setProjectInitialized(hasSlides);

        if (hasSlides) {
          // Select first slide if none selected or old slide not in new list
          if (!currentSlide || !list.some((s: SlideInfo) => s.name === currentSlide)) {
            setCurrentSlide(list[0].name);
          } else {
            // Reload current slide content to sync
            loadSlideContent(currentSlide);
          }
        } else if (autoInitIfEmpty) {
          // Auto initialize project workspace for new session
          initProjectWorkspace(sessionId);
        } else {
          setCurrentSlide(null);
          setSvgContent('');
          setSlideAnnotations({});
        }
      })
      .catch(() => {
        setProjectInitialized(false);
        if (autoInitIfEmpty) {
          initProjectWorkspace(sessionId);
        }
      });
  };

  // Load single slide SVG content and annotations
  const loadSlideContent = (slideName: string) => {
    fetch(`/api/slide/${encodeURIComponent(slideName)}`)
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          console.error('Failed to load slide content:', data.error);
          return;
        }
        setSvgContent(data.content || '');
        
        // Build annotations object
        const anns: Record<string, string> = {};
        (data.annotations || []).forEach((ann: any) => {
          anns[ann.element_id] = ann.annotation;
        });
        setSlideAnnotations(anns);
        
        // Reset element selection if it doesn't exist in new SVG
        if (selectedElementId && !data.content.includes(`id="${selectedElementId}"`)) {
          setSelectedElementId(null);
          setSelectedElementTag(null);
        }
      })
      .catch(err => {
        console.error('Error fetching slide:', err);
      });
  };

  // Initialize workspace for session
  const initProjectWorkspace = (sessionId: string) => {
    if (initLoading) return;
    setInitLoading(true);
    setStatusText('Initializing...');
    
    fetch('/api/projects/init', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        session_id: sessionId,
        format: 'ppt169'
      })
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setProjectInitialized(true);
          checkAndLoadSlides(sessionId, false);
        } else {
          throw new Error(data.detail || 'Initialization failed');
        }
      })
      .catch(err => {
        console.error('Initialization error:', err);
      })
      .finally(() => {
        setInitLoading(false);
        setStatusText('Ready');
      });
  };

  // Create new session
  const handleCreateSession = () => {
    if (agentRunning) return;
    const newId = crypto.randomUUID();
    setSessionCookie(newId);
    window.history.pushState(null, '', `/${newId}`);
    
    const newSess: ChatSession = {
      id: newId,
      title: 'New Presentation Project',
      timestamp: Date.now()
    };
    const updated = [newSess, ...sessions];
    setSessions(updated);
    localStorage.setItem('ppt_sessions', JSON.stringify(updated));
    
    // Switch states
    setProjectInitialized(false);
    setSlides([]);
    setCurrentSlide(null);
    setSvgContent('');
    setSlideAnnotations({});
    setSelectedElementId(null);
    setSelectedElementTag(null);
    setMessages([
      {
        role: 'assistant',
        content: 'Hello! I am your AI Presentation Assistant. I can help you generate presentation slide decks page-by-page. Describe the topic you want to write about to begin!'
      }
    ]);
    setActiveSessionId(newId);
  };

  // Select existing session
  const handleSelectSession = (id: string) => {
    if (agentRunning) return;
    setSessionCookie(id);
    window.history.pushState(null, '', `/${id}`);
    setActiveSessionId(id);
  };

  // Delete session
  const handleDeleteSession = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (agentRunning) return;
    
    const updated = sessions.filter(s => s.id !== id);
    setSessions(updated);
    localStorage.setItem('ppt_sessions', JSON.stringify(updated));

    if (activeSessionId === id) {
      if (updated.length > 0) {
        handleSelectSession(updated[0].id);
      } else {
        handleCreateSession();
      }
    }
  };

  // Send message and stream agent response
  const handleSendMessage = async (textToSend?: string) => {
    const prompt = (textToSend || chatInput).trim();
    if (!prompt || agentRunning) return;

    setChatInput('');
    setAgentRunning(true);
    setStatusText('Thinking...');
    setActiveLogs([]);

    // Add user message
    const userMsg: Message = { role: 'user', content: prompt };
    setMessages(prev => [...prev, userMsg]);

    // Update session title if default
    const currentSession = sessions.find(s => s.id === activeSessionId);
    if (currentSession && currentSession.title === 'New Presentation Project') {
      const truncated = prompt.length > 22 ? `${prompt.substring(0, 19)}...` : prompt;
      const updated = sessions.map(s => s.id === activeSessionId ? { ...s, title: truncated } : s);
      setSessions(updated);
      localStorage.setItem('ppt_sessions', JSON.stringify(updated));
    }

    try {
      const response = await fetch('/api/agent/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ prompt })
      });

      if (!response.ok) {
        throw new Error(`Server returned error ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      if (!reader) throw new Error('ReadableStream not supported');

      let activeMessagesList = [...messages, userMsg];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          try {
            const update = JSON.parse(trimmed);
            if (update.error) {
              throw new Error(update.error);
            }

            // Find if there is an update for 'agent' node
            if (update.agent) {
              setStatusText('Formulating answer...');
              const agentMsgs: Message[] = update.agent.messages || [];
              
              agentMsgs.forEach(msg => {
                const duplicateIndex = activeMessagesList.findIndex(
                  existing => 
                    existing.role === msg.role && 
                    ((msg.id && existing.id === msg.id) ||
                     (existing.content === msg.content && 
                      JSON.stringify(existing.tool_calls) === JSON.stringify(msg.tool_calls)))
                );
                
                if (duplicateIndex === -1) {
                  activeMessagesList.push(msg);
                } else {
                  activeMessagesList[duplicateIndex] = {
                    ...activeMessagesList[duplicateIndex],
                    ...msg
                  };
                }
              });
              setMessages([...activeMessagesList]);
            }

            // Find if there is an update for 'tools' node
            if (update.tools) {
              setStatusText('Executing tools...');
              const toolMsgs: Message[] = update.tools.messages || [];
              
              toolMsgs.forEach(msg => {
                const duplicateIndex = activeMessagesList.findIndex(
                  existing => 
                    existing.role === 'tool' && 
                    existing.tool_call_id === msg.tool_call_id && 
                    msg.tool_call_id !== undefined
                );
                
                if (duplicateIndex === -1) {
                  activeMessagesList.push(msg);
                } else {
                  activeMessagesList[duplicateIndex] = {
                    ...activeMessagesList[duplicateIndex],
                    ...msg
                  };
                }
              });
              setMessages([...activeMessagesList]);
              
              // Auto reload slides when tools execute
              checkAndLoadSlides(activeSessionId, false);
            }

          } catch (e: any) {
            console.error('Error parsing NDJSON chunk line:', trimmed, e);
          }
        }
      }

      // Process remaining content in buffer
      if (buffer.trim()) {
        try {
          const update = JSON.parse(buffer.trim());
          if (update.error) {
            throw new Error(update.error);
          }
          if (update.agent) {
            const agentMsgs: Message[] = update.agent.messages || [];
            agentMsgs.forEach(msg => {
              const duplicateIndex = activeMessagesList.findIndex(
                existing => 
                  existing.role === msg.role && 
                  ((msg.id && existing.id === msg.id) ||
                   (existing.content === msg.content && 
                    JSON.stringify(existing.tool_calls) === JSON.stringify(msg.tool_calls)))
              );
              if (duplicateIndex === -1) {
                activeMessagesList.push(msg);
              } else {
                activeMessagesList[duplicateIndex] = { ...activeMessagesList[duplicateIndex], ...msg };
              }
            });
            setMessages([...activeMessagesList]);
          }
          if (update.tools) {
            const toolMsgs: Message[] = update.tools.messages || [];
            toolMsgs.forEach(msg => {
              const duplicateIndex = activeMessagesList.findIndex(
                existing => 
                  existing.role === 'tool' && 
                  existing.tool_call_id === msg.tool_call_id && 
                  msg.tool_call_id !== undefined
              );
              if (duplicateIndex === -1) {
                activeMessagesList.push(msg);
              } else {
                activeMessagesList[duplicateIndex] = { ...activeMessagesList[duplicateIndex], ...msg };
              }
            });
            setMessages([...activeMessagesList]);
            checkAndLoadSlides(activeSessionId, false);
          }
        } catch (e) {
          console.error('Error parsing final buffer chunk:', buffer, e);
        }
      }

    } catch (err: any) {
      console.error('Agent run stream failed:', err);
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `❌ Execution Failed: ${err.message}`
        }
      ]);
    } finally {
      setAgentRunning(false);
      setStatusText('Ready');
      setActiveLogs([]);
      checkAndLoadSlides(activeSessionId, false);
    }
  };

  // Export native PPTX file
  const handleExportPptx = () => {
    if (agentRunning) return;
    setAgentRunning(true);
    setStatusText('Exporting...');
    setMessages(prev => [
      ...prev,
      {
        role: 'assistant',
        content: '⏳ Exporting presentation slides to a native PowerPoint PPTX presentation... This may take a few seconds.'
      }
    ]);

    fetch('/api/projects/export', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        transition: 'fade',
        animation: 'auto',
        no_merge: false
      })
    })
      .then(res => {
        if (!res.ok) throw new Error('Export service returned error');
        return res.json();
      })
      .then(() => {
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: '🎉 PowerPoint PPTX file exported successfully! Downloading the deck...'
          }
        ]);
        window.location.href = '/api/projects/download';
      })
      .catch(err => {
        console.error('Export failed:', err);
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: `❌ PPTX Export failed: ${err.message}`
          }
        ]);
      })
      .finally(() => {
        setAgentRunning(false);
        setStatusText('Ready');
      });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // SVG elements click handler to select an element
  const handleSvgClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as SVGElement;
    if (!target) return;
    
    const svgRoot = e.currentTarget.querySelector('svg');
    if (target === svgRoot) {
      setSelectedElementId(null);
      setSelectedElementTag(null);
      return;
    }
    
    const picked = target.closest('[id]') as SVGElement;
    if (picked && picked !== svgRoot) {
      setSelectedElementId(picked.id);
      setSelectedElementTag(picked.tagName.toLowerCase());
      
      // Load current annotation into textarea if exists
      setAnnotationInput(slideAnnotations[picked.id] || '');
    } else {
      setSelectedElementId(null);
      setSelectedElementTag(null);
    }
  };

  // Add annotation to slide
  const handleAddAnnotation = () => {
    if (!currentSlide || !selectedElementId) return;
    
    const annotation = annotationInput.trim();
    if (!annotation) return;

    fetch(`/api/slide/${encodeURIComponent(currentSlide)}/annotate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        element_id: selectedElementId,
        annotation: annotation
      })
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'ok') {
          setSlideAnnotations(prev => ({
            ...prev,
            [selectedElementId]: annotation
          }));
          setAnnotationsDirty(true);
          setAnnotationInput('');
          setSelectedElementId(null);
          setSelectedElementTag(null);
        } else {
          alert('Failed to add annotation');
        }
      })
      .catch(err => {
        console.error('Add annotation failed:', err);
      });
  };

  // Remove annotation from slide
  const handleRemoveAnnotation = (elemId: string) => {
    if (!currentSlide) return;

    fetch(`/api/slide/${encodeURIComponent(currentSlide)}/annotate/${encodeURIComponent(elemId)}`, {
      method: 'DELETE'
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'ok') {
          setSlideAnnotations(prev => {
            const updated = { ...prev };
            delete updated[elemId];
            return updated;
          });
          setAnnotationsDirty(true);
        }
      })
      .catch(err => {
        console.error('Delete annotation failed:', err);
      });
  };

  // Submit and save all staged edits to disk
  const handleApplyChanges = () => {
    if (!currentSlide) return;

    setStatusText('Saving...');
    fetch('/api/save-all', { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'ok') {
          setAnnotationsDirty(false);
          setStatusText('Ready');
          // Reload slides & current content to sync from disk
          checkAndLoadSlides(activeSessionId, false);
          
          setMessages(prev => [
            ...prev,
            {
              role: 'assistant',
              content: '💾 Staged annotations applied and written to project files successfully! You can tell me to optimize slides based on these instructions.'
            }
          ]);
        } else {
          alert('Failed to apply changes to disk');
        }
      })
      .catch(err => {
        console.error('Apply changes failed:', err);
        setStatusText('Ready');
      });
  };

  // Navigate slides
  const handlePrevSlide = () => {
    if (slides.length <= 1 || !currentSlide) return;
    const idx = slides.findIndex(s => s.name === currentSlide);
    if (idx > 0) {
      setCurrentSlide(slides[idx - 1].name);
    }
  };

  const handleNextSlide = () => {
    if (slides.length <= 1 || !currentSlide) return;
    const idx = slides.findIndex(s => s.name === currentSlide);
    if (idx >= 0 && idx < slides.length - 1) {
      setCurrentSlide(slides[idx + 1].name);
    }
  };

  const currentIdx = currentSlide ? slides.findIndex(s => s.name === currentSlide) : -1;

  // Group tool messages by their corresponding tool_call_id
  const toolResultsMap = new Map<string, Message>();
  messages.forEach((msg) => {
    if (msg.role === 'tool' && msg.tool_call_id) {
      toolResultsMap.set(msg.tool_call_id, msg);
    }
  });

  return (
    <div className="app-container">
      {/* 1. Sidebar - Recent Chat Sessions */}
      <div className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <Presentation size={24} />
            <span className="sidebar-title">PPT Master</span>
          </div>
          <span className="sidebar-subtitle">AI Presentation Agent</span>
        </div>
        <button 
          className="new-chat-btn"
          onClick={handleCreateSession}
          disabled={agentRunning}
        >
          <Plus size={16} />
          <span>New Project</span>
        </button>
        <div className="sessions-list">
          <div className="sessions-list-header">Recent Chats</div>
          {sessions.map(s => (
            <div
              key={s.id}
              className={`session-item ${activeSessionId === s.id ? 'active' : ''}`}
              onClick={() => handleSelectSession(s.id)}
            >
              <div className="session-info">
                <MessageSquare size={14} className="session-icon shrink-0" />
                <span className="session-title">{s.title}</span>
              </div>
              <div className="session-actions">
                <button
                  className="session-action-btn delete"
                  onClick={(e) => handleDeleteSession(s.id, e)}
                  disabled={agentRunning}
                  title="Delete Project"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 2. Chat Panel - Dialogue & Live Logs */}
      <div className={`chat-panel ${chatCollapsed ? 'collapsed' : ''} ${editorCollapsed ? 'expanded' : ''}`}>
        <div className="chat-header">
          <span className="chat-header-title">AI Copilot</span>
          <div className="chat-status">
            <span className={`status-dot ${agentRunning ? 'orange' : 'green'}`} />
            <span>{statusText}</span>
          </div>
          <button 
            className="collapse-btn" 
            onClick={() => setChatCollapsed(true)}
            title="Collapse Chat"
          >
            <ChevronLeft size={16} />
          </button>
        </div>

        <div className="chat-messages">
          {messages.map((m, idx) => {
            if (m.role === 'tool' || m.role === 'system') return null;
            return (
              <div key={idx} className={`chat-message-row ${m.role}`}>
                <div className="chat-bubble">
                  {m.content && (
                    <div 
                      className="message-text"
                      dangerouslySetInnerHTML={{
                        __html: m.content
                          .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                          .replace(/`([^`]+)`/g, '<code>$1</code>')
                          .replace(/\n/g, '<br />')
                      }}
                    />
                  )}
                  
                  {/* Structured tool calls pipeline */}
                  {m.tool_calls && m.tool_calls.length > 0 && (
                    <div style={{ marginTop: '12px' }}>
                      {renderToolCalls(m.tool_calls, toolResultsMap)}
                    </div>
                  )}

                  {/* Collapsible log history details */}
                  {m.logLines && m.logLines.length > 0 && (
                    <div style={{ marginTop: '12px' }}>
                      {renderStructuredLogs(m.logLines)}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Running Live stream loader */}
          {agentRunning && (
            <div className="chat-message-row assistant">
              <div className="chat-bubble">
                <div className="chat-loading">
                  <span></span><span></span><span></span>
                  <span style={{ fontSize: '11px', color: '#64748b', marginLeft: '8px', fontWeight: 500 }}>
                    {statusText === 'Thinking...' ? 'Agent is formulating plan...' : 'Agent is executing tools...'}
                  </span>
                </div>
              </div>
            </div>
          )}

          <div ref={chatMessagesEndRef} />
        </div>

        <div className="chat-input-container">
          <div className="quick-prompts">
            <button 
              className="quick-prompt-btn"
              onClick={() => handleSendMessage('请为我生成一份关于量子计算的PPT，共5页，内容包括其基本原理、发展现状、硬件架构以及未来展望')}
              disabled={agentRunning}
            >
              生成量子计算PPT
            </button>
            <button 
              className="quick-prompt-btn"
              onClick={() => handleSendMessage('请根据我刚才在右侧添加的标注，优化当前这页幻灯片的布局排版')}
              disabled={agentRunning || !projectInitialized}
            >
              根据标注优化排版
            </button>
          </div>
          <div className="input-row">
            <textarea
              className="chat-textarea"
              placeholder="Ask Copilot to generate or edit..."
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={agentRunning}
            />
            <button 
              className="send-btn"
              onClick={() => handleSendMessage()}
              disabled={agentRunning || !chatInput.trim()}
            >
              <Send size={16} />
            </button>
          </div>
          <div className="actions-row">
            <button 
              className="action-btn gold-btn"
              onClick={handleExportPptx}
              disabled={agentRunning || !projectInitialized}
            >
              <Download size={14} />
              <span>Export PPTX</span>
            </button>
          </div>
        </div>
      </div>

      {/* Collapsed Chat Panel Button */}
      {chatCollapsed && (
        <div 
          className="collapsed-chat-trigger"
          onClick={() => setChatCollapsed(false)}
          title="Expand Chat"
        >
          <ChevronRight size={20} />
        </div>
      )}

      {/* Collapsed Editor Panel Button */}
      {editorCollapsed && (
        <div 
          className="collapsed-editor-trigger"
          onClick={() => setEditorCollapsed(false)}
          title="Expand Preview"
        >
          <ChevronLeft size={20} />
        </div>
      )}

      {/* 3. Editor Panel - Clean SVG Render Preview & Annotations Panel */}
      <div className={`editor-container ${editorCollapsed ? 'collapsed' : ''}`}>
        {projectInitialized && slides.length > 0 ? (
          <div className="editor-grid">
            {/* Dynamic CSS styles to highlight annotated and selected SVG elements */}
            {selectedElementId && (
              <style>{`
                .preview-canvas svg #${selectedElementId} {
                  outline: 2.5px solid #2563eb !important;
                  outline-offset: 1px;
                }
              `}</style>
            )}
            {Object.keys(slideAnnotations).length > 0 && (
              <style>{`
                ${Object.keys(slideAnnotations).map(id => `.preview-canvas svg #${id} { outline: 1.5px dashed #f59e0b !important; outline-offset: 0.5px; }`).join('\n')}
              `}</style>
            )}

            {/* Sub-panel 1: Slides list */}
            <div className="slides-sidebar">
              <div className="panel-section-title">Slides List</div>
              {slides.map((s, idx) => (
                <div
                  key={s.name}
                  className={`slide-card ${currentSlide === s.name ? 'active' : ''} ${s.ok === false ? 'error' : ''}`}
                  onClick={() => setCurrentSlide(s.name)}
                  title={s.ok === false ? `Parsing Error: ${s.error || ''}` : s.name}
                >
                  <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '2px' }}>Page {idx + 1}</div>
                  <div className="truncate text-xs font-semibold">{s.name}</div>
                  {s.annotation_count > 0 && (
                    <span 
                      style={{ 
                        fontSize: '9px', 
                        padding: '1px 5px', 
                        background: '#f59e0b', 
                        color: 'white', 
                        borderRadius: '10px',
                        display: 'inline-block',
                        marginTop: '4px',
                        fontWeight: 700
                      }}
                    >
                      {s.annotation_count} annot.
                    </span>
                  )}
                </div>
              ))}
            </div>

            {/* Sub-panel 2: Selected SVG Slide preview */}
            <div className="canvas-area">
              <div className="canvas-header">
                <span className="canvas-slide-name">{currentSlide || 'No slide selected'}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div className="canvas-nav">
                    <button 
                      className="canvas-nav-btn"
                      onClick={handlePrevSlide}
                      disabled={slides.length <= 1 || currentIdx <= 0}
                      title="Previous Slide"
                    >
                      <ChevronLeft size={16} />
                    </button>
                    <span className="canvas-page-info">
                      {currentIdx >= 0 ? `${currentIdx + 1} / ${slides.length}` : '— / —'}
                    </span>
                    <button 
                      className="canvas-nav-btn"
                      onClick={handleNextSlide}
                      disabled={slides.length <= 1 || currentIdx === -1 || currentIdx === slides.length - 1}
                      title="Next Slide"
                    >
                      <ChevronRight size={16} />
                    </button>
                  </div>
                  <button 
                    className="collapse-btn" 
                    onClick={() => setEditorCollapsed(true)}
                    title="Collapse Preview"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>

              <div className="preview-viewport">
                {svgContent ? (
                  <div 
                    className="preview-canvas"
                    style={{ aspectRatio: getSvgAspectRatio(svgContent) }}
                    onClick={handleSvgClick}
                    dangerouslySetInnerHTML={{ __html: svgContent }}
                  />
                ) : (
                  <div style={{ color: '#94a3b8', fontSize: '14px', fontStyle: 'italic' }}>
                    Loading slide canvas...
                  </div>
                )}
              </div>
            </div>

            {/* Sub-panel 3: Slide annotations editor */}
            <div className="annotations-panel">
              <div className="panel-section-title">Visual Editor</div>
              
              {selectedElementId ? (
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <div className="panel-section-title" style={{ fontSize: '10px', marginTop: '8px' }}>Selected Element</div>
                  <div className="selected-element-card">
                    <span className="tag-name">&lt;{selectedElementTag}&gt;</span>
                    <span className="elem-id">#{selectedElementId}</span>
                  </div>

                  <div className="panel-section-title" style={{ fontSize: '10px' }}>Edit Instruction</div>
                  <textarea
                    className="annotation-textarea"
                    placeholder="Describe how AI should modify this element (e.g. 'change color to blue', 'make font size larger')..."
                    value={annotationInput}
                    onChange={e => setAnnotationInput(e.target.value)}
                  />
                  <button 
                    className="new-chat-btn" 
                    style={{ margin: '0 0 16px 0', padding: '8px' }}
                    onClick={handleAddAnnotation}
                    disabled={!annotationInput.trim()}
                  >
                    Add Annotation
                  </button>
                </div>
              ) : (
                <div style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '12px', padding: '10px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', marginBottom: '16px' }}>
                  Click any element on the slide preview to add a change instruction.
                </div>
              )}

              <div className="panel-section-title" style={{ borderTop: '1px solid #e2e8f0', paddingTop: '16px', marginTop: '8px' }}>
                Annotations on Slide
              </div>
              <div className="annotation-list-container">
                {Object.keys(slideAnnotations).length === 0 ? (
                  <div style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '12.5px', padding: '4px 0' }}>
                    No annotations on this slide yet.
                  </div>
                ) : (
                  Object.entries(slideAnnotations).map(([elemId, annText]) => (
                    <div key={elemId} className="annotation-item-card">
                      <div className="annotation-item-header">
                        <span className="annotation-item-id">#{elemId}</span>
                        <button 
                          className="annotation-item-delete"
                          onClick={() => handleRemoveAnnotation(elemId)}
                          title="Delete Instruction"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                      <div className="annotation-item-text">{annText}</div>
                    </div>
                  ))
                )}
              </div>

              <button 
                className="apply-btn"
                onClick={handleApplyChanges}
                disabled={!annotationsDirty}
              >
                <FileCheck size={14} />
                <span>Apply Changes</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="welcome-screen">
            {initLoading ? (
              <div className="welcome-card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                <Presentation size={48} className="welcome-icon animate-pulse" />
                <h2 className="welcome-title">Initializing Workspace...</h2>
                <p className="welcome-desc">Creating project directories and preparing canvas templates on disk...</p>
              </div>
            ) : (
              <div className="welcome-card">
                <Presentation size={48} className="welcome-icon mx-auto" />
                <h2 className="welcome-title">Preparing AI Presentation Workspace</h2>
                <p className="welcome-desc">
                  Workspace is being set up automatically for your session. Waiting for workspace files...
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default App;
