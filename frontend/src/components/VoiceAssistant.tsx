import React, { useState, useEffect, useRef } from 'react';
import {
  Mic,
  MicOff,
  Radio,
  Send,
  Square,
  Volume2,
  VolumeX,
  Zap,
  Activity,
  AlertCircle,
} from 'lucide-react';
import { createVoiceSession, type VoiceSessionDto } from '../services/api';
import { VoiceClient, type VoiceState, type VoiceMetrics } from '../services/voiceSocket';

interface ChatTurn {
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
  metrics?: VoiceMetrics;
}

export function VoiceAssistant() {
  const [session, setSession] = useState<VoiceSessionDto | null>(null);
  const [voiceState, setVoiceState] = useState<VoiceState>('disconnected');
  const [providerMode, setProviderMode] = useState<'modular' | 'realtime'>('modular');
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [textInput, setTextInput] = useState('');
  const [lastMetrics, setLastMetrics] = useState<VoiceMetrics | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [speechOutputEnabled, setSpeechOutputEnabled] = useState(true);

  const clientRef = useRef<VoiceClient | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const speakText = (text: string) => {
    if (!speechOutputEnabled || !('speechSynthesis' in window)) return;
    try {
      window.speechSynthesis.cancel();
      // Remove markdown asterisks or code formatting for cleaner speech
      const cleanText = text.replace(/[*#`_~]/g, '').trim();
      if (!cleanText) return;
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.rate = 1.05;
      utterance.pitch = 1.0;
      const voices = window.speechSynthesis.getVoices();
      const preferred = voices.find(
        (v) =>
          v.lang.startsWith('en') &&
          (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Jenny') || v.name.includes('David'))
      );
      if (preferred) utterance.voice = preferred;
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      console.warn('Speech synthesis error:', e);
    }
  };

  // Initialize VoiceClient
  useEffect(() => {
    const client = new VoiceClient({
      onSessionReady: (sessionId) => {
        console.log('Voice session ready:', sessionId);
        setErrorMsg(null);
      },
      onUserTranscript: (text) => {
        setTurns((prev) => [
          ...prev,
          {
            role: 'user',
            text,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          },
        ]);
      },
      onAssistantTranscript: (text) => {
        setTurns((prev) => [
          ...prev,
          {
            role: 'assistant',
            text,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          },
        ]);
        speakText(text);
      },
      onTurnComplete: (metrics) => {
        setLastMetrics(metrics);
        setTurns((prev) => {
          if (prev.length === 0) return prev;
          const copy = [...prev];
          copy[copy.length - 1].metrics = metrics;
          return copy;
        });
      },
      onInterrupted: () => {
        console.log('Voice turn interrupted by user.');
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
      },
      onError: (err) => {
        setErrorMsg(err);
      },
      onStateChange: (state) => {
        setVoiceState(state);
        setIsRecording(state === 'listening');
      },
    });

    clientRef.current = client;

    return () => {
      client.disconnect();
    };
  }, []);

  // Auto-scroll transcript to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns]);

  const handleStartSession = async () => {
    setErrorMsg(null);
    try {
      const newSession = await createVoiceSession(providerMode);
      setSession(newSession);
      if (clientRef.current) {
        await clientRef.current.connect(newSession.session_id);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to start voice session.');
    }
  };

  const handleEndSession = () => {
    if (clientRef.current) {
      clientRef.current.disconnect();
    }
    setSession(null);
    setIsRecording(false);
  };

  const toggleRecording = async () => {
    if (!clientRef.current || voiceState === 'disconnected') return;

    if (isRecording) {
      clientRef.current.stopRecording();
    } else {
      await clientRef.current.startRecording();
    }
  };

  const handleSendText = (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim() || !clientRef.current) return;
    clientRef.current.sendText(textInput.trim());
    setTextInput('');
  };

  const handleInterrupt = () => {
    if (clientRef.current) {
      clientRef.current.interrupt();
    }
  };

  const handleQuickPrompt = (prompt: string) => {
    if (!clientRef.current || voiceState === 'disconnected') return;
    clientRef.current.sendText(prompt);
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(340px, 420px) 1fr', gap: '24px' }}>
      {/* Left Column: Voice Orb & Live Controls */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* Voice Engine Controller Card */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <span style={{ fontSize: '0.82rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
              Voice Engine (Phase 2)
            </span>
            <div
              className={`badge ${
                voiceState === 'speaking'
                  ? 'badge-info'
                  : voiceState === 'listening'
                  ? 'badge-warning'
                  : voiceState === 'connected'
                  ? 'badge-success'
                  : 'badge-error'
              }`}
            >
              <Radio size={12} className={voiceState !== 'disconnected' ? 'pulse' : ''} />
              {voiceState.toUpperCase()}
            </div>
          </div>

          {/* Glowing Animated Voice Orb */}
          <div
            style={{
              height: '180px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative',
              margin: '10px 0 20px 0',
            }}
          >
            <div
              style={{
                width: isRecording ? '110px' : voiceState === 'speaking' ? '120px' : '90px',
                height: isRecording ? '110px' : voiceState === 'speaking' ? '120px' : '90px',
                borderRadius: '50%',
                background:
                  voiceState === 'speaking'
                    ? 'radial-gradient(circle, #38bdf8 0%, #0284c7 70%)'
                    : isRecording
                    ? 'radial-gradient(circle, #f87171 0%, #dc2626 70%)'
                    : voiceState === 'connected'
                    ? 'radial-gradient(circle, #6366f1 0%, #4338ca 70%)'
                    : 'radial-gradient(circle, #475569 0%, #1e293b 70%)',
                boxShadow:
                  voiceState === 'speaking'
                    ? '0 0 45px rgba(56, 189, 248, 0.6)'
                    : isRecording
                    ? '0 0 45px rgba(239, 68, 68, 0.7)'
                    : voiceState === 'connected'
                    ? '0 0 35px rgba(99, 102, 241, 0.5)'
                    : 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                cursor: voiceState !== 'disconnected' ? 'pointer' : 'default',
              }}
              onClick={toggleRecording}
              title={isRecording ? 'Click to finish speaking' : 'Click to start speaking'}
            >
              {isRecording ? (
                <Mic size={42} color="#ffffff" />
              ) : voiceState === 'speaking' ? (
                <Volume2 size={42} color="#ffffff" />
              ) : voiceState !== 'disconnected' ? (
                <Mic size={36} color="#e0e7ff" />
              ) : (
                <MicOff size={32} color="#94a3b8" />
              )}
            </div>

            <span style={{ marginTop: '14px', fontSize: '0.85rem', color: '#cbd5e1', fontWeight: 500 }}>
              {isRecording
                ? 'Listening... Click to send speech'
                : voiceState === 'processing'
                ? 'Processing STT & LLM...'
                : voiceState === 'speaking'
                ? 'Nexus speaking (Audio playing)'
                : voiceState === 'connected'
                ? 'Click Orb or Mic button to talk'
                : 'Session offline'}
            </span>
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', gap: '10px', marginBottom: '16px' }}>
            {voiceState === 'disconnected' ? (
              <button
                onClick={handleStartSession}
                style={{
                  background: 'linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)',
                  color: '#ffffff',
                  flex: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                }}
              >
                <Zap size={16} /> Start Voice Session
              </button>
            ) : (
              <>
                <button
                  onClick={toggleRecording}
                  style={{
                    background: isRecording ? '#dc2626' : '#4f46e5',
                    color: '#ffffff',
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                  }}
                >
                  {isRecording ? <Square size={16} /> : <Mic size={16} />}
                  {isRecording ? 'Stop & Send' : 'Speak Now'}
                </button>

                <button
                  onClick={handleInterrupt}
                  disabled={voiceState !== 'speaking'}
                  title="Interrupt assistant speech immediately"
                  style={{
                    background: 'rgba(239, 68, 68, 0.15)',
                    color: '#f87171',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <VolumeX size={16} /> Interrupt
                </button>

                <button
                  onClick={handleEndSession}
                  style={{
                    background: 'rgba(255, 255, 255, 0.08)',
                    color: '#94a3b8',
                  }}
                >
                  End
                </button>
              </>
            )}
          </div>

          {/* Mode Selector & TTS Output */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '0.8rem',
              color: '#94a3b8',
              borderTop: '1px solid rgba(255, 255, 255, 0.08)',
              paddingTop: '12px',
              flexWrap: 'wrap',
              gap: '8px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>Mode:</span>
              <button
                onClick={() => setProviderMode('modular')}
                disabled={voiceState !== 'disconnected'}
                style={{
                  padding: '3px 8px',
                  fontSize: '0.72rem',
                  background: providerMode === 'modular' ? '#4f46e5' : 'transparent',
                  color: providerMode === 'modular' ? '#ffffff' : '#94a3b8',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                }}
              >
                Modular
              </button>
              <button
                onClick={() => setProviderMode('realtime')}
                disabled={voiceState !== 'disconnected'}
                style={{
                  padding: '3px 8px',
                  fontSize: '0.72rem',
                  background: providerMode === 'realtime' ? '#4f46e5' : 'transparent',
                  color: providerMode === 'realtime' ? '#ffffff' : '#94a3b8',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                }}
              >
                Realtime
              </button>
            </div>

            <button
              onClick={() => {
                if (speechOutputEnabled && 'speechSynthesis' in window) {
                  window.speechSynthesis.cancel();
                }
                setSpeechOutputEnabled(!speechOutputEnabled);
              }}
              style={{
                padding: '4px 10px',
                fontSize: '0.75rem',
                background: speechOutputEnabled ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255, 255, 255, 0.05)',
                color: speechOutputEnabled ? '#38bdf8' : '#64748b',
                border: speechOutputEnabled ? '1px solid rgba(56, 189, 248, 0.3)' : '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                cursor: 'pointer',
              }}
              title="Toggle speech synthesis voice output"
            >
              {speechOutputEnabled ? <Volume2 size={13} /> : <VolumeX size={13} />}
              TTS Voice: {speechOutputEnabled ? 'ON' : 'MUTED'}
            </button>
          </div>
        </div>

        {/* Latency & Turn Profiling Card */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '0.82rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
              Turn Performance & Latency
            </span>
            <Activity size={16} color="#38bdf8" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <div style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '10px', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>STT Latency</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#38bdf8' }}>
                {lastMetrics?.stt_latency_ms !== undefined ? `${lastMetrics.stt_latency_ms} ms` : '—'}
              </div>
            </div>

            <div style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '10px', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>LLM Latency</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#a78bfa' }}>
                {lastMetrics?.llm_latency_ms !== undefined ? `${lastMetrics.llm_latency_ms} ms` : '—'}
              </div>
            </div>

            <div style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '10px', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>TTS Latency</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#34d399' }}>
                {lastMetrics?.tts_latency_ms !== undefined ? `${lastMetrics.tts_latency_ms} ms` : '—'}
              </div>
            </div>

            <div style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '10px', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>Total End-to-End</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fbbf24' }}>
                {lastMetrics?.total_latency_ms !== undefined ? `${lastMetrics.total_latency_ms} ms` : '—'}
              </div>
            </div>
          </div>
        </div>

        {/* Quick Test Phrases */}
        <div className="card">
          <span style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '10px', fontWeight: 600 }}>
            Simulate Quick Voice Query:
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {[
              'What tasks are scheduled for today?',
              'Search my recent emails for interview invitations.',
              'Check my calendar availability tomorrow afternoon.',
            ].map((p, idx) => (
              <button
                key={idx}
                onClick={() => handleQuickPrompt(p)}
                disabled={voiceState === 'disconnected'}
                style={{
                  textAlign: 'left',
                  fontSize: '0.78rem',
                  padding: '8px 12px',
                  background: 'rgba(255, 255, 255, 0.04)',
                  color: '#cbd5e1',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                }}
              >
                "{p}"
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Right Column: Live Conversation Transcript */}
      <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '620px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            paddingBottom: '14px',
            marginBottom: '16px',
          }}
        >
          <div>
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc' }}>
              Voice Conversation Transcript
            </h3>
            <p style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              Turn management, transcription logging, and spoken response stream
            </p>
          </div>
          {session && (
            <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
              Session: {session.session_id.substring(0, 8)}...
            </span>
          )}
        </div>

        {/* Error notification if any */}
        {errorMsg && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: '8px',
              fontSize: '0.82rem',
              background: 'rgba(239, 68, 68, 0.15)',
              color: '#f87171',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              marginBottom: '14px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <AlertCircle size={16} /> {errorMsg}
          </div>
        )}

        {/* Message History List */}
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '14px', paddingRight: '8px' }}>
          {turns.length === 0 ? (
            <div
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#64748b',
                textAlign: 'center',
              }}
            >
              <Mic size={36} style={{ marginBottom: '12px', opacity: 0.4 }} />
              <p style={{ fontSize: '0.9rem', fontWeight: 500 }}>No voice turns yet.</p>
              <p style={{ fontSize: '0.78rem', color: '#64748b', maxWidth: '320px', marginTop: '4px' }}>
                Start a session and click "Speak Now" or choose a prompt to begin conversing with Nexus.
              </p>
            </div>
          ) : (
            turns.map((turn, i) => (
              <div
                key={i}
                style={{
                  alignSelf: turn.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '82%',
                  background: turn.role === 'user' ? 'rgba(79, 70, 229, 0.25)' : 'rgba(255, 255, 255, 0.05)',
                  border: `1px solid ${turn.role === 'user' ? 'rgba(99, 102, 241, 0.4)' : 'rgba(255, 255, 255, 0.1)'}`,
                  borderRadius: '12px',
                  padding: '12px 16px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px', gap: '16px' }}>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      color: turn.role === 'user' ? '#a5b4fc' : '#38bdf8',
                      textTransform: 'uppercase',
                    }}
                  >
                    {turn.role === 'user' ? 'You (Spoken)' : 'Nexus (Spoken)'}
                  </span>
                  <span style={{ fontSize: '0.7rem', color: '#64748b' }}>{turn.timestamp}</span>
                </div>
                <p style={{ fontSize: '0.9rem', color: '#f1f5f9', lineHeight: 1.45 }}>{turn.text}</p>
                {turn.metrics && (
                  <div style={{ marginTop: '6px', fontSize: '0.7rem', color: '#94a3b8', borderTop: '1px solid rgba(255, 255, 255, 0.06)', paddingTop: '4px' }}>
                    Latency: {turn.metrics.total_latency_ms} ms (STT: {turn.metrics.stt_latency_ms ?? 0}ms, LLM: {turn.metrics.llm_latency_ms ?? 0}ms, TTS: {turn.metrics.tts_latency_ms ?? 0}ms)
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Text Input Footer for Mixed Modality */}
        <form
          onSubmit={handleSendText}
          style={{
            display: 'flex',
            gap: '10px',
            marginTop: '16px',
            borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            paddingTop: '14px',
          }}
        >
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            disabled={voiceState === 'disconnected'}
            placeholder={
              voiceState === 'disconnected'
                ? 'Start a session to talk or type...'
                : 'Type a message (spoken reply will play)...'
            }
            style={{
              flex: 1,
              padding: '10px 14px',
              borderRadius: '8px',
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: '#ffffff',
              fontSize: '0.88rem',
            }}
          />
          <button
            type="submit"
            disabled={voiceState === 'disconnected' || !textInput.trim()}
            style={{
              background: '#4f46e5',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Send size={15} /> Send
          </button>
        </form>
      </div>
    </div>
  );
}
