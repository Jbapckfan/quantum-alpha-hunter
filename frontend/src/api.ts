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

async function post<T>(path: string, body?: unknown): Promise<T> {
  const opts: RequestInit = { method: 'POST' };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? `Request failed: ${path}`);
  }
  return res.json();
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Delete failed: ${path}`);
}

// ─── Stock Scanner ───────────────────────────────────────────────────

export function scanPatterns(minScore = 35): Promise<ScanResponse> {
  return get(`/api/scan?min_score=${minScore}`);
}

export function getHighConfidence(minScore = 70): Promise<ScanResponse> {
  return get(`/api/scan/high-confidence?min_score=${minScore}`);
}

export function analyzeStock(ticker: string): Promise<AnalysisResponse> {
  return get(`/api/analyze/${ticker}`);
}

// ─── Watchlist ───────────────────────────────────────────────────────

export function getWatchlist(): Promise<WatchlistResponse> {
  return get('/api/watchlist');
}

export function getPerformance(): Promise<PerformanceResponse> {
  return get('/api/watchlist/performance');
}

export async function addToWatchlist(ticker: string, notes = ''): Promise<void> {
  await post(`/api/watchlist/add-from-scan/${ticker}?notes=${encodeURIComponent(notes)}`);
}

export function removeFromWatchlist(ticker: string): Promise<void> {
  return del(`/api/watchlist/${ticker}`);
}

export function addAllHighConfidence(minScore = 75): Promise<{ added: string[] }> {
  return post(`/api/scan/high-confidence/add-all?min_score=${minScore}`);
}

// ─── Crypto Scanner ──────────────────────────────────────────────────

export function scanCrypto(minScore = 15): Promise<CryptoScanResponse> {
  return get(`/api/crypto/scan?min_score=${minScore}`);
}

export function getCryptoQuote(ticker: string): Promise<unknown> {
  return get(`/api/crypto/quote/${ticker}`);
}

export function analyzeCrypto(ticker: string): Promise<unknown> {
  return get(`/api/crypto/analyze/${ticker}`);
}

export function getCryptoFullAnalysis(ticker: string, days = 90): Promise<CryptoFullAnalysis> {
  return get(`/api/crypto/chart/${ticker}?days=${days}`);
}

export function getCryptoChart(ticker: string, days = 90): Promise<unknown> {
  return get(`/api/crypto/chart/${ticker}?days=${days}`);
}

export function getCryptoSentiment(ticker: string): Promise<unknown> {
  return get(`/api/crypto/sentiment/${ticker}`);
}

export function getFearGreedIndex(): Promise<FearGreedResponse> {
  return get('/api/crypto/fear-greed');
}

export function getTrendingCrypto(): Promise<unknown> {
  return get('/api/crypto/top-movers');
}

// ─── Options ─────────────────────────────────────────────────────────

export function getOptionsChain(ticker: string, expiration?: string): Promise<OptionsChain> {
  const qs = expiration ? `&targetDate=${expiration}` : '';
  return get(`/api/options/chain?ticker=${ticker}${qs}`);
}

export function scanLeaps(minScore = 0.6): Promise<LeapsScanResponse> {
  return get(`/api/options/leaps?min_trend=${minScore}`);
}

export function scanZeroDte(ticker = 'SPY'): Promise<ZeroDteScanResponse> {
  return get(`/api/options/zero-dte?ticker=${ticker}`);
}

export function findStrategies(
  ticker: string,
  targetPrice: number,
  maxRisk?: number,
): Promise<StrategyFinderResponse> {
  return post('/api/options/strategy', {
    ticker,
    target_price: targetPrice,
    target_date: new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10),
    view: targetPrice > 0 ? 'bull' : 'bear',
    capital: maxRisk ?? 5000,
  });
}

// ─── Covered Calls ───────────────────────────────────────────────────

export function getCoveredCalls(
  ticker: string,
  strategy: string,
  expiration?: string,
): Promise<unknown> {
  return post('/api/options/covered-calls', {
    ticker,
    strategy,
  });
}

// ─── Resistance / Analysis ───────────────────────────────────────────

export function getResistanceLevels(ticker: string): Promise<AnalysisResponse> {
  return get(`/api/analyze/${ticker}`);
}

// ─── Signal Weights ──────────────────────────────────────────────────

export function getWeights(): Promise<WeightsResponse> {
  return get('/api/weights');
}
