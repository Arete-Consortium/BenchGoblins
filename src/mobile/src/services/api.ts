import axios from 'axios';
import { DecisionRequest, DecisionResponse, Player } from '../types';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function healthCheck(): Promise<{ status: string; version: string }> {
  const response = await api.get('/health');
  return response.data;
}

export async function searchPlayers(
  query: string,
  sport: string,
  limit: number = 10
): Promise<Player[]> {
  const response = await api.post('/players/search', { query, sport, limit });
  return response.data;
}

export async function makeDecision(request: DecisionRequest): Promise<DecisionResponse> {
  const response = await api.post('/decide', request);
  return response.data;
}

export async function getDecisionHistory(limit: number = 20): Promise<DecisionResponse[]> {
  const response = await api.get('/history', { params: { limit } });
  return response.data;
}

export default api;
