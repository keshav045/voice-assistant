/**
 * Voice WebSocket Client with microphone capture, audio streaming, and audio playback.
 */

export interface VoiceMetrics {
  stt_latency_ms?: number;
  llm_latency_ms?: number;
  tts_latency_ms?: number;
  total_latency_ms?: number;
}

export interface VoiceEventCallbacks {
  onSessionReady?: (sessionId: string) => void;
  onUserTranscript?: (text: string) => void;
  onAssistantTranscript?: (text: string) => void;
  onTurnComplete?: (metrics: VoiceMetrics) => void;
  onInterrupted?: () => void;
  onError?: (error: string) => void;
  onStateChange?: (state: VoiceState) => void;
}

export type VoiceState = 'disconnected' | 'connecting' | 'connected' | 'listening' | 'processing' | 'speaking';

export class VoiceClient {
  private ws: WebSocket | null = null;
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private currentAudio: HTMLAudioElement | null = null;
  private pingInterval: any = null;
  private callbacks: VoiceEventCallbacks = {};
  public state: VoiceState = 'disconnected';
  public sessionId: string | null = null;

  constructor(callbacks: VoiceEventCallbacks) {
    this.callbacks = callbacks;
  }

  private setState(newState: VoiceState) {
    this.state = newState;
    this.callbacks.onStateChange?.(newState);
  }

  /**
   * Connect to backend voice WebSocket.
   */
  public async connect(sessionId: string): Promise<void> {
    this.sessionId = sessionId;
    this.setState('connecting');

    let wsUrl: string;
    const apiBase = import.meta.env.VITE_API_BASE_URL;
    if (apiBase) {
      const wsProto = apiBase.startsWith('https') ? 'wss:' : 'ws:';
      const cleanHost = apiBase.replace(/^https?:\/\//, '').replace(/\/$/, '');
      wsUrl = `${wsProto}//${cleanHost}/ws/voice/${sessionId}`;
    } else {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host;
      wsUrl = `${protocol}//${host}/ws/voice/${sessionId}`;
    }

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.setState('connected');
        // Start 25-second keepalive ping
        this.pingInterval = setInterval(() => {
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000);
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleIncomingEvent(data);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      this.ws.onerror = (err) => {
        console.error('WebSocket voice error:', err);
        this.callbacks.onError?.('WebSocket connection error.');
      };

      this.ws.onclose = () => {
        this.setState('disconnected');
        clearInterval(this.pingInterval);
      };
    } catch (err: any) {
      this.setState('disconnected');
      this.callbacks.onError?.(err.message || 'Failed to connect WebSocket');
    }
  }

  private handleIncomingEvent(event: any) {
    switch (event.type) {
      case 'session_ready':
        this.callbacks.onSessionReady?.(event.session_id);
        break;

      case 'transcript_user':
        this.callbacks.onUserTranscript?.(event.text);
        break;

      case 'transcript_assistant':
        this.callbacks.onAssistantTranscript?.(event.text);
        break;

      case 'audio':
        this.playAudioPayload(event.data, event.format || 'mp3');
        break;

      case 'turn_complete':
        this.callbacks.onTurnComplete?.(event.metrics || {});
        break;

      case 'interrupted':
        this.stopAudioPlayback();
        this.callbacks.onInterrupted?.();
        this.setState('connected');
        break;

      case 'pong':
        // Keepalive acknowledged
        break;

      case 'error':
        this.callbacks.onError?.(event.message);
        this.setState('connected');
        break;

      default:
        console.log('Unhandled voice event:', event);
    }
  }

  /**
   * Start recording user speech via browser microphone.
   */
  public async startRecording(): Promise<void> {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.callbacks.onError?.('Microphone access is not supported by your browser.');
      return;
    }

    try {
      this.stopAudioPlayback(); // Stop any ongoing assistant audio
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.audioChunks = [];

      const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4';
      this.mediaRecorder = new MediaRecorder(stream, { mimeType });

      this.mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          this.audioChunks.push(e.data);
        }
      };

      this.mediaRecorder.onstop = async () => {
        // Stream collected audio blob as base64 to backend
        const audioBlob = new Blob(this.audioChunks, { type: mimeType });
        await this.sendAudioBlob(audioBlob, mimeType.includes('webm') ? 'webm' : 'wav');
        // Stop stream tracks
        stream.getTracks().forEach((track) => track.stop());
      };

      this.mediaRecorder.start();
      this.setState('listening');
    } catch (err: any) {
      console.error('Microphone permission error:', err);
      this.callbacks.onError?.(err.message || 'Microphone access denied.');
      this.setState('connected');
    }
  }

  /**
   * Stop recording and send audio turn.
   */
  public stopRecording(): void {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.setState('processing');
      this.mediaRecorder.stop();
    }
  }

  private async sendAudioBlob(blob: Blob, format: string): Promise<void> {
    const reader = new FileReader();
    reader.readAsDataURL(blob);
    reader.onloadend = () => {
      const base64Data = (reader.result as string).split(',')[1];
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(
          JSON.stringify({
            type: 'audio',
            data: base64Data,
            format: format,
          })
        );
      }
    };
  }

  /**
   * Send text turn directly (for typing into voice interface).
   */
  public sendText(text: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.stopAudioPlayback();
      this.setState('processing');
      this.ws.send(JSON.stringify({ type: 'text', text }));
    }
  }

  /**
   * Play base64 audio payload from assistant.
   */
  private playAudioPayload(base64Audio: string, format: string): void {
    this.stopAudioPlayback();
    try {
      const audioUrl = `data:audio/${format};base64,${base64Audio}`;
      this.currentAudio = new Audio(audioUrl);
      this.setState('speaking');

      this.currentAudio.onended = () => {
        this.setState('connected');
      };

      this.currentAudio.onerror = () => {
        this.setState('connected');
      };

      this.currentAudio.play().catch((e) => {
        console.warn('Audio autoplay blocked or failed:', e);
        this.setState('connected');
      });
    } catch (err) {
      console.error('Audio playback error:', err);
      this.setState('connected');
    }
  }

  /**
   * Stop ongoing audio playback immediately and notify backend.
   */
  public interrupt(): void {
    this.stopAudioPlayback();
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'interrupt' }));
    }
    this.setState('connected');
  }

  private stopAudioPlayback(): void {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
      this.currentAudio = null;
    }
  }

  /**
   * Disconnect voice session.
   */
  public disconnect(): void {
    this.stopAudioPlayback();
    clearInterval(this.pingInterval);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setState('disconnected');
  }
}
