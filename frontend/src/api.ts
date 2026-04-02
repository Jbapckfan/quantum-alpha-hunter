import type {
  ScanResponse,
  AnalysisResponse,
  WatchlistResponse,
  PerformanceResponse,
  CryptoScanResponse,
  CryptoFullAnalysis,
  FearGreedResponse,
  OptionsChain,
  LeapsScanResponse,
  ZeroDteScanResponse,
  StrategyFinderResponse,
  WeightsResponse,
} from './types';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ─── Helpers ─────────────────────────────────────────────────────────

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${path}`);
  }
  return res.json();
}

async function post<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'POST' });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${path}`);
  }
  return res.json();
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Delete failed: ${path}`);
}

// ─── Stock Scanner ───────────────────────────────────────────────────

export function scanPatterns(minScore = 35): Promise<ScanResponse> {
  return get(`/scan?min_score=${minScore}`);
}

export function getHighConfidence(minScore = 70): Promise<ScanResponse> {
  return get(`/high-confidence?min_score=${minScore}`);
}

export function analyzeStock(ticker: string): Promise<AnalysisResponse> {
  return get(`/analyze/${ticker}`);
}

// ─── Watchlist ───────────────────────────────────────────────────────

export function getWatchlist(): Promise<WatchlistResponse> {
  return get('/watchlist');
}

export function getPerformance(): Promise<PerformanceResponse> {
  return get('/watchlist/performance');
}

export async function addToWatchlist(ticker: string, notes = ''): Promise<void> {
  await post(`/watchlist/add-from-scan/${ticker}?notes=${encodeURIComponent(notes)}`);
}

export function removeFromWatchlist(ticker: string): Promise<void> {
  return del(`/watchlist/${ticker}`);
}

export function addAllHighConfidence(minScore = 75): Promise<{ added: string[] }> {
  return post(`/high-confidence/add-all?min_score=${minScore}`);
}

// ─── Crypto Scanner ──────────────────────────────────────────────────

export function scanCrypto(minScore = 15): Promise<CryptoScanResponse> {
  return get(`/crypto/scan?min_score=${minScore}`);
}

export function getCryptoQuote(ticker: string): Promise<unknown> {
  return get(`/crypto/quote/${ticker}`);
}

export function analyzeCrypto(ticker: string): Promise<unknown> {
  return get(`/crypto/analyze/${ticker}`);
}

export function getCryptoFullAnalysis(ticker: string, days = 90): Promise<CryptoFullAnalysis> {
  return get(`/crypto/full-analysis/${ticker}?days=${days}`);
}

export function getCryptoChart(ticker: string, days = 90): Promise<unknown> {
  return get(`/crypto/chart/${ticker}?days=${days}`);
}

export function getCryptoSentiment(ticker: string): Promise<unknown> {
  return get(`/crypto/sentiment/${ticker}`);
}

export function getFearGreedIndex(): Promise<FearGreedResponse> {
  return get('/crypto/fear-greed');
}

export function getTrendingCrypto(): Promise<unknown> {
  return get('/crypto/trending');
}

// ─── Options ─────────────────────────────────────────────────────────

export function getOptionsChain(ticker: string, expiration?: string): Promise<OptionsChain> {
  const qs = expiration ? `?expiration=${expiration}` : '';
  return get(`/options/chain/${ticker}${qs}`);
}

export function scanLeaps(minScore = 50): Promise<LeapsScanResponse> {
  return get(`/options/leaps?min_score=${minScore}`);
}

export function scanZeroDte(): Promise<ZeroDteScanResponse> {
  return get('/options/0dte');
}

export function findStrategies(
  ticker: string,
  targetPrice: number,
  maxRisk?: number,
): Promise<StrategyFinderResponse> {
  let qs = `?target_price=${targetPrice}`;
  if (maxRisk !== undefined) qs += `&max_risk=${maxRisk}`;
  return get(`/options/strategies/${ticker}${qs}`);
}

// ─── Covered Calls ───────────────────────────────────────────────────

export function getCoveredCalls(
  ticker: string,
  strategy: string,
  expiration?: string,
): Promise<unknown> {
  let qs = `?strategy=${strategy}`;
  if (expiration) qs += `&expiration=${expiration}`;
  return get(`/options/covered-calls/${ticker}${qs}`);
}

// ─── Resistance / Analysis ───────────────────────────────────────────

export function getResistanceLevels(ticker: string): Promise<AnalysisResponse> {
  return get(`/analyze/${ticker}`);
}

// ─── Signal Weights ──────────────────────────────────────────────────

export function getWeights(): Promise<WeightsResponse> {
  return get('/weights');
}
