export interface DatabaseHealth {
  status: 'connected' | 'disconnected';
  dialect: string;
  latency_ms?: number;
  error?: string;
}

export interface SystemHealth {
  status: 'healthy' | 'degraded';
  project: string;
  version: string;
  environment: string;
  database: DatabaseHealth;
  timestamp?: string;
}

export interface SystemConfig {
  project_name: string;
  version: string;
  environment: string;
  debug: boolean;
  api_v1_prefix: string;
  ai: {
    model: string;
    voice_model: string;
    embedding_model: string;
    embedding_dimension: number;
    api_key_configured: boolean;
  };
  capabilities: string[];
}

export interface User {
  id: string;
  email: string;
  full_name?: string | null;
  is_active: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

