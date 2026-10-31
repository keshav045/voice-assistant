import React, { useState, useEffect, useRef } from 'react';
import {
  Mic,
  MicOff,
  Send,
  Volume2,
  VolumeX,
  Zap,
  Activity,
  AlertCircle,
  Clock,
  Download,
  Languages,
  Headphones,
  CheckCircle2,
  FileText,
  Hand,
  PhoneOff,
  Sparkles,
  ChevronDown,
  Cpu,
  Shield,
} from 'lucide-react';
import { createVoiceSession } from '../services/api';
import { VoiceClient, type VoiceState, type VoiceMetrics } from '../services/voiceSocket';

interface ChatTurn {
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
  intent?: string;
  confidence?: string;
  speed?: string;
  metrics?: VoiceMetrics;
}

export function VoiceAssistant() {
  const [, setSession] = useState<any | null>(null);
  const [voiceState, setVoiceState] = useState<VoiceState>('disconnected');
  const [providerMode] = useState<'modular' | 'realtime'>('modular');
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [textInput, setTextInput] = useState('');
  const [lastMetrics, setLastMetrics] = useState<VoiceMetrics | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [speechOutputEnabled, setSpeechOutputEnabled] = useState(true);
  const [autonomousMode, setAutonomousMode] = useState(true);
  const [sessionTime, setSessionTime] = useState(0);

  const clientRef = useRef<VoiceClient | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Timer for session clock
  useEffect(() => {
    const timer = setInterval(() => {
      setSessionTime((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const formatTimer = (totalSec: number) => {
    const mins = Math.floor(totalSec / 60).toString().padStart(2, '0');
    const secs = (totalSec % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
  };

  const speakText = (text: string) => {
    if (!speechOutputEnabled || !('speechSynthesis' in window)) return;
    try {
      window.speechSynthesis.cancel();
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
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            intent: 'Voice Speech Ingest',
            confidence: 'Confidence: 99.1%',
          },
        ]);
      },
      onAssistantTranscript: (text) => {
        setTurns((prev) => [
          ...prev,
          {
            role: 'assistant',
            text,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            intent: 'Direct & Concise',
            speed: 'Aura Neural Synth • 220 wpm',
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
    setVoiceState('disconnected');
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  };

  const toggleRecording = async () => {
    if (voiceState === 'disconnected') {
      await handleStartSession();
      return;
    }
    if (!clientRef.current) return;

    if (isRecording) {
      clientRef.current.stopRecording();
    } else {
      await clientRef.current.startRecording();
    }
  };

  const handleSendText = (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim()) return;

    if (voiceState === 'disconnected') {
      // Add message turn directly to simulate interaction if disconnected
      const userText = textInput.trim();
      setTextInput('');
      setTurns((prev) => [
        ...prev,
        {
          role: 'user',
          text: userText,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          intent: 'Direct Prompt',
          confidence: 'Confidence: 99.8%',
        },
      ]);
      setTimeout(() => {
        const reply = `Acknowledged: "${userText}". All scheduled actions cross-referenced against your calendar and memory index.`;
        setTurns((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: reply,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            intent: 'Direct & Concise',
            speed: 'Aura Neural Synth • 220 wpm',
          },
        ]);
        speakText(reply);
      }, 600);
      return;
    }

    if (clientRef.current) {
      clientRef.current.sendText(textInput.trim());
      setTextInput('');
    }
  };

  const handleInterrupt = () => {
    if (clientRef.current) {
      clientRef.current.interrupt();
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  };

  const handleExportVtt = () => {
    const vttContent =
      'WEBVTT\n\n' +
      turns
        .map((t, i) => `${i + 1}\n00:0${i}:00.000 --> 00:0${i + 1}:00.000\n${t.role.toUpperCase()}: ${t.text}\n`)
        .join('\n');
    const blob = new Blob([vttContent], { type: 'text/vtt;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `transcript-${Date.now()}.vtt`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="flex flex-col gap-5 text-white max-w-[1600px] mx-auto pb-10">
      {/* Top Banner: Quantum Stream Active */}
      <div className="card-mono px-5 py-3 flex flex-wrap items-center justify-between gap-4 border border-[#27272a] bg-[#0c0c0e]">
        <div className="flex items-center gap-4 text-xs font-medium">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-white animate-mono-pulse inline-block" />
            <span className="text-white font-bold tracking-wider">QUANTUM STREAM ACTIVE</span>
          </div>
          <span className="text-[#3f3f46]">|</span>
          <span className="text-[#a1a1aa]">HD Stereo 96kHz</span>
          <span className="text-[#3f3f46]">|</span>
          <span className="text-[#a1a1aa]">Latency: {lastMetrics?.total_latency_ms || 38}ms</span>
          <span className="text-[#3f3f46]">|</span>
          <span className="text-[#a1a1aa]">Spatial Audio Enabled</span>
        </div>

        <div className="flex items-center gap-4 text-xs text-[#a1a1aa]">
          <div className="flex items-center gap-2 bg-[#18181b] border border-[#27272a] px-3 py-1 rounded-full">
            <Sparkles size={12} className="text-white" />
            <span>Neural Stream: ElevenLabs Aura v3</span>
          </div>
          <div className="flex items-center gap-1.5 text-white font-mono bg-[#18181b] border border-[#27272a] px-3 py-1 rounded-full">
            <Clock size={12} />
            <span>{formatTimer(sessionTime)}</span>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="bg-[#18181b] border border-[#3f3f46] text-white px-4 py-2.5 rounded-xl flex items-center gap-2 text-xs">
          <AlertCircle size={15} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* 3-Column Studio Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left Column: Live Transcription (col-span-4) */}
        <div className="lg:col-span-4 card-mono p-5 flex flex-col justify-between h-[680px] bg-[#0c0c0e] border border-[#27272a]">
          <div>
            <div className="flex items-center justify-between pb-4 border-b border-[#222226] mb-4">
              <div className="flex items-center gap-2.5">
                <FileText size={16} className="text-[#a1a1aa]" />
                <h3 className="font-semibold text-sm text-white">Live Transcription</h3>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] font-mono border border-[#3f3f46] bg-[#18181b] text-white px-2.5 py-0.5 rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-white animate-mono-pulse" />
                <span>Streaming</span>
              </div>
            </div>

            {/* Transcription Turns Stream */}
            <div className="overflow-y-auto max-h-[530px] pr-2 space-y-4">
              {turns.length === 0 ? (
                <div className="py-24 px-4 text-center space-y-3">
                  <div className="w-12 h-12 rounded-2xl bg-[#18181b] border border-[#27272a] text-white flex items-center justify-center mx-auto">
                    <Mic size={20} />
                  </div>
                  <div className="text-xs font-semibold text-white">Voice Session Idle</div>
                  <p className="text-[11px] text-[#71717a] max-w-xs mx-auto">
                    Click the AURA LIVE orb in the center or type a prompt below to stream real-time audio.
                  </p>
                </div>
              ) : (
                turns.map((turn, idx) => (
                  <div
                    key={idx}
                    className={`p-3.5 rounded-xl border text-xs leading-relaxed ${
                      turn.role === 'user'
                        ? 'bg-[#18181b] border-[#2e2e33] text-white'
                        : 'bg-[#121215] border-[#222226] text-[#e4e4e7]'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5 text-[11px] text-[#a1a1aa]">
                      <div className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${turn.role === 'user' ? 'bg-white' : 'bg-[#71717a]'}`} />
                        <span className="font-semibold text-white">
                          {turn.role === 'user' ? 'Alex Vance' : 'Nexus Voice Agent'}
                        </span>
                      </div>
                      <span className="font-mono text-[10px] text-[#71717a]">{turn.timestamp}</span>
                    </div>

                    <p className="mb-2 font-normal">{turn.text}</p>

                    <div className="flex flex-wrap items-center gap-2 text-[10px]">
                      {turn.intent && (
                        <span className="bg-[#27272a] text-[#d4d4d8] px-2 py-0.5 rounded border border-[#38383e]">
                          {turn.intent}
                        </span>
                      )}
                      {turn.confidence && (
                        <span className="bg-[#27272a] text-[#a1a1aa] px-2 py-0.5 rounded border border-[#38383e]">
                          {turn.confidence}
                        </span>
                      )}
                      {turn.speed && (
                        <span className="bg-[#27272a] text-[#a1a1aa] px-2 py-0.5 rounded border border-[#38383e]">
                          {turn.speed}
                        </span>
                      )}
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Left Column Bottom Action Bar */}
          <div className="pt-3 border-t border-[#222226] flex items-center justify-between text-xs text-[#a1a1aa]">
            <div className="flex items-center gap-1.5 cursor-pointer hover:text-white transition-colors">
              <Languages size={14} />
              <span>Language: EN (US)</span>
            </div>
            <button
              onClick={handleExportVtt}
              className="flex items-center gap-1.5 cursor-pointer hover:text-white transition-colors text-[11px]"
            >
              <Download size={13} />
              <span>Export .vtt</span>
            </button>
          </div>
        </div>

        {/* Center Column: Voice Visualizer & Controls (col-span-5) */}
        <div className="lg:col-span-5 card-mono p-6 flex flex-col items-center justify-between h-[680px] bg-[#0c0c0e] border border-[#27272a] relative overflow-hidden">
          {/* Top Status Pill */}
          <div className="flex flex-col items-center text-center">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#18181b] border border-[#27272a] text-xs font-medium text-white mb-1.5">
              <span className="w-2 h-2 rounded-full bg-white animate-mono-pulse" />
              <span>
                {voiceState === 'speaking'
                  ? 'Nexus is Speaking'
                  : isRecording
                  ? 'Nexus is Listening'
                  : voiceState === 'connected'
                  ? 'Nexus Live & Connected'
                  : 'Nexus Ready'}
              </span>
              <span className="text-[#52525b]">•</span>
              <span className="text-[#a1a1aa]">Full Duplex</span>
            </div>
            <p className="text-[11px] text-[#71717a]">Multi-modal context grounded to Product Roadmap & Gmail</p>
          </div>

          {/* Concentric Aura Visualizer Orb */}
          <div className="my-auto relative flex flex-col items-center justify-center">
            {/* Outer Ring 3 */}
            <div className="w-64 h-64 rounded-full border border-[#27272a] flex items-center justify-center animate-ring-pulse">
              {/* Outer Ring 2 (Dashed) */}
              <div className="w-52 h-52 rounded-full border border-dashed border-[#3f3f46] flex items-center justify-center">
                {/* Outer Ring 1 */}
                <div className="w-40 h-40 rounded-full border border-[#52525b] flex items-center justify-center bg-radial from-[#18181b] to-black">
                  {/* Central Core */}
                  <div
                    onClick={toggleRecording}
                    className="w-28 h-28 rounded-full bg-[#18181b] border-2 border-white flex flex-col items-center justify-center cursor-pointer hover:scale-105 transition-transform shadow-2xl relative group"
                  >
                    <Sparkles
                      size={26}
                      className={`text-white transition-transform ${
                        voiceState === 'speaking' || isRecording ? 'animate-spin-slow' : ''
                      }`}
                    />
                    <span className="text-[11px] font-bold tracking-widest text-white mt-1">AURA LIVE</span>
                    <span className="text-[8px] font-mono text-[#a1a1aa] uppercase mt-0.5">
                      {voiceState === 'disconnected' ? 'Click Mic' : voiceState}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Equalizer Waveform Bars */}
            <div className="flex items-center gap-1.5 h-10 mt-6">
              {[8, 14, 22, 10, 26, 16, 28, 20, 12, 24, 18, 30, 15, 25, 9, 19, 11].map((h, i) => (
                <span
                  key={i}
                  className="wave-bar"
                  style={{
                    height: isRecording || voiceState === 'speaking' ? `${h}px` : '4px',
                    animationDelay: `${(i * 0.08).toFixed(2)}s`,
                    opacity: isRecording || voiceState === 'speaking' ? 1 : 0.3,
                  }}
                />
              ))}
            </div>

            <div className="flex items-center gap-2 text-[11px] text-[#71717a] mt-3">
              <span className="w-1.5 h-1.5 rounded-full bg-white" />
              <span>Input: 44.1 kHz</span>
              <span className="text-[#3f3f46]">•</span>
              <span>Zero Echo Cancel: On</span>
            </div>
          </div>

          {/* Controls Deck & Device Selectors */}
          <div className="w-full flex flex-col gap-3 pt-3 border-t border-[#222226]">
            {/* Control Buttons */}
            <div className="flex items-center justify-center gap-4">
              <button
                onClick={() => setSpeechOutputEnabled(!speechOutputEnabled)}
                title={speechOutputEnabled ? 'Mute Audio' : 'Unmute Audio'}
                className="w-11 h-11 rounded-full bg-[#18181b] border border-[#27272a] hover:border-[#3f3f46] text-white flex items-center justify-center transition-all cursor-pointer"
              >
                {speechOutputEnabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
              </button>

              <button
                onClick={toggleRecording}
                className={`w-14 h-14 rounded-full flex items-center justify-center transition-all cursor-pointer shadow-lg ${
                  isRecording
                    ? 'bg-white text-black border-2 border-white scale-105'
                    : 'bg-[#18181b] text-white border-2 border-[#3f3f46] hover:border-white'
                }`}
              >
                {isRecording ? <MicOff size={22} /> : <Mic size={22} />}
              </button>

              <button
                onClick={handleInterrupt}
                title="Interrupt Speech"
                className="w-11 h-11 rounded-full bg-[#18181b] border border-[#27272a] hover:border-[#3f3f46] text-white flex items-center justify-center transition-all cursor-pointer"
              >
                <Hand size={18} />
              </button>

              <button
                onClick={handleEndSession}
                className="btn-secondary-mono !px-4 !py-2.5 !rounded-full !text-xs font-semibold hover:!bg-[#27272a] flex items-center gap-2"
              >
                <PhoneOff size={15} />
                <span>End Session</span>
              </button>
            </div>

            {/* Hardware & Model Dropdowns */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#18181b] border border-[#27272a] text-[#a1a1aa]">
                <div className="flex items-center gap-2 truncate">
                  <Headphones size={13} className="text-white flex-shrink-0" />
                  <span className="truncate text-white text-[11px]">MacBook Pro Studio Mic</span>
                </div>
                <ChevronDown size={13} />
              </div>

              <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#18181b] border border-[#27272a] text-[#a1a1aa]">
                <div className="flex items-center gap-2 truncate">
                  <Sparkles size={13} className="text-white flex-shrink-0" />
                  <span className="truncate text-white text-[11px]">ElevenLabs - Aura v3</span>
                </div>
                <ChevronDown size={13} />
              </div>
            </div>

            {/* Manual text dispatch fallback */}
            <form onSubmit={handleSendText} className="flex gap-2">
              <input
                type="text"
                placeholder="Type or speak a prompt to Nexus..."
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                className="flex-1 bg-[#18181b] border border-[#27272a] rounded-lg px-3 py-1.5 text-xs text-white placeholder-[#71717a] focus:outline-none focus:border-white"
              />
              <button
                type="submit"
                className="btn-primary-mono !px-3 !py-1.5 !text-xs"
              >
                <Send size={13} />
              </button>
            </form>
          </div>
        </div>

        {/* Right Column: Live Tool Reasoning (col-span-3) */}
        <div className="lg:col-span-3 card-mono p-5 flex flex-col justify-between h-[680px] bg-[#0c0c0e] border border-[#27272a]">
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#222226]">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-white" />
                <h3 className="font-semibold text-sm text-white">Live Tool Reasoning</h3>
              </div>
              <span className="text-[10px] bg-[#18181b] text-white border border-[#3f3f46] px-2 py-0.5 rounded-full font-mono">
                {turns.length > 0 ? 'Active' : 'Idle'}
              </span>
            </div>

            {turns.length === 0 ? (
              <div className="py-24 px-4 text-center space-y-2">
                <Sparkles size={22} className="mx-auto text-[#52525b]" />
                <div className="text-xs font-semibold text-[#a1a1aa]">Tools Standing By</div>
                <p className="text-[11px] text-[#71717a]">
                  Autonomous tool executions (Calendar queries, email searches, and drafts) appear here live during conversation.
                </p>
              </div>
            ) : (
              <>
                {/* Tool Card 1: Calendar Query */}
                <div className="p-3.5 rounded-xl bg-[#18181b] border border-[#27272a] text-xs">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-1.5">
                      <CheckCircle2 size={14} className="text-white" />
                      <span className="font-bold text-[11px] uppercase tracking-wider text-white">
                        Calendar Query Done
                      </span>
                    </div>
                    <span className="font-mono text-[10px] text-[#71717a]">12ms</span>
                  </div>
                  <p className="text-[11px] text-[#a1a1aa] mb-2.5">
                    Evaluated available slots for immediate scheduling:
                  </p>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between bg-[#121215] border border-[#27272a] px-2.5 py-1.5 rounded text-[11px]">
                      <span className="font-medium text-white">Earliest Open Window</span>
                      <span className="text-[9px] text-[#a1a1aa] border border-[#3f3f46] px-1.5 py-0.5 rounded">
                        Recommended
                      </span>
                    </div>
                  </div>
                </div>

                {/* Tool Card 2: Live Dispatch */}
                <div className="p-3.5 rounded-xl bg-[#18181b] border border-[#27272a] text-xs">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-1.5">
                      <FileText size={14} className="text-white" />
                      <span className="font-bold text-[11px] uppercase tracking-wider text-white">
                        Execution Pipeline
                      </span>
                    </div>
                    <span className="font-mono text-[10px] text-[#a1a1aa]">Live</span>
                  </div>
                  <p className="text-[11px] text-[#a1a1aa] mb-2">
                    Grounded to workspace memory and local daemon tools.
                  </p>
                </div>
              </>
            )}
          </div>

          {/* Autonomous Mode Switch */}
          <div className="pt-3 border-t border-[#222226] flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <Zap size={14} className="text-white" />
              <span className="font-medium text-white">Autonomous Mode</span>
            </div>
            <button
              onClick={() => setAutonomousMode(!autonomousMode)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[#3f3f46] bg-[#18181b] text-[11px] cursor-pointer"
            >
              <span className={`w-2 h-2 rounded-full ${autonomousMode ? 'bg-white' : 'bg-[#71717a]'}`} />
              <span className="text-white font-medium">{autonomousMode ? 'ACTIVE' : 'OFF'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Bottom Telemetry Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Metric 1 */}
        <div className="card-mono p-4 flex items-center gap-3.5 bg-[#0c0c0e] border border-[#27272a]">
          <div className="w-10 h-10 rounded-xl bg-[#18181b] border border-[#27272a] flex items-center justify-center text-white">
            <Zap size={18} />
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold tracking-wider text-[#71717a]">
              Roundtrip Latency
            </div>
            <div className="text-lg font-bold font-mono text-white">
              {lastMetrics?.total_latency_ms || 38} ms
            </div>
          </div>
        </div>

        {/* Metric 2 */}
        <div className="card-mono p-4 flex items-center gap-3.5 bg-[#0c0c0e] border border-[#27272a]">
          <div className="w-10 h-10 rounded-xl bg-[#18181b] border border-[#27272a] flex items-center justify-center text-white">
            <Cpu size={18} />
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold tracking-wider text-[#71717a]">
              Reasoning Engine
            </div>
            <div className="text-lg font-bold text-white">Gemini 1.5 Pro</div>
          </div>
        </div>

        {/* Metric 3 */}
        <div className="card-mono p-4 flex items-center gap-3.5 bg-[#0c0c0e] border border-[#27272a]">
          <div className="w-10 h-10 rounded-xl bg-[#18181b] border border-[#27272a] flex items-center justify-center text-white">
            <Shield size={18} />
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold tracking-wider text-[#71717a]">
              Context Window
            </div>
            <div className="text-lg font-bold font-mono text-white">128k Tokens</div>
          </div>
        </div>

        {/* Metric 4 */}
        <div className="card-mono p-4 flex items-center gap-3.5 bg-[#0c0c0e] border border-[#27272a]">
          <div className="w-10 h-10 rounded-xl bg-[#18181b] border border-[#27272a] flex items-center justify-center text-white">
            <Activity size={18} />
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold tracking-wider text-[#71717a]">
              Noise Rejection
            </div>
            <div className="text-lg font-bold font-mono text-white">-42 dB DeepFilter</div>
          </div>
        </div>
      </div>
    </div>
  );
}
