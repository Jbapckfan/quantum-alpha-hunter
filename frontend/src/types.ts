// ─── Stock Scanner Types ─────────────────────────────────────────────

export interface PatternResult {
  ticker: string;
  name: string;
  sector?: string;
  industry?: string;
  description?: string;
  price: number;
  score: number;
  flags: string[];
  drawdown: number;
  rally_from_low: number;
  base_tightness: number;
  vol_expansion: number;
  best_day: number;
  rsi: number;
  ema_bullish: boolean;
  macd_bullish: boolean;
  stop: number;
  R: number;
  t1: number;
  t2: number;
  t3: number;
  t4: number;
  pct_to_t2: number;
  pct_to_10r: number;
  mcap_m: number;
  high_52w: number;
  low_52w: number;
  target_mean: number | null;
  target_high: number | null;
  upside_to_target: number | null;
  num_analysts: number;
  recommendation: string;
  upgrades: Upgrade[];
  stage: 'EARLY' | 'MID' | 'LATE' | 'EXTENDED';
  confidence?: string;
  bullish_signals?: number;
}

export interface Upgrade {
  date: string;
  firm: string;
  toGrade: string;
  fromGrade?: string;
  action: string;
  currentTarget?: number | null;
  priorTarget?: number | null;
}

export interface ScanResponse {
  scan_time: string;
  total: number;
  min_score: number;
  results: PatternResult[];
}

export interface ResistanceLevel {
  level: number;
  strength: number;
  pct_above: number;
}

export interface AnalysisResponse {
  ticker: string;
  analysis: {
    ticker: string;
    current_price: number;
    swing_high: number;
    swing_low: number;
    key_levels: ResistanceLevel[];
    details: {
      swing_highs: number[];
      volume_clusters: number[];
      round_numbers: number[];
      gap_levels: number[];
      moving_averages: [string, number][];
      fibonacci: [string, number][];
    };
  };
  pattern: PatternResult | null;
  chart: string;
  generated_at: string;
}

// ─── Watchlist Types ─────────────────────────────────────────────────

export interface WatchlistItem {
  ticker: string;
  company_name?: string;
  sector?: string;
  industry?: string;
  entry_price: number;
  score: number;
  flags: string[];
  target_price: number | null;
  stop_price: number | null;
  notes: string | null;
  added_at: string;
  status: string;
  current_price?: number;
  pnl?: number;
  pnl_pct?: number;
  pattern_data?: {
    drawdown: number;
    rally_from_low: number;
    stage: string;
    t1?: number;
    t2?: number;
    t3?: number;
    t4?: number;
  };
}

export interface WatchlistResponse {
  items: WatchlistItem[];
  total: number;
  last_updated: string | null;
}

export interface PerformanceResponse {
  total_positions: number;
  active_positions: number;
  winners: number;
  losers: number;
  win_rate: number;
  avg_pnl_pct: number;
  total_pnl_pct: number;
}

// ─── Crypto Types ────────────────────────────────────────────────────

export interface CryptoResult {
  ticker: string;
  name: string;
  price: number;
  score: number;
  max_score: number;
  signals_triggered: number;
  trend: 'BULLISH' | 'RECOVERING' | 'NEUTRAL' | 'BEARISH';
  flags: string[];
  signal_breakdown: Record<string, number>;
  change_24h: number;
  change_7d: number;
  change_30d: number;
  volume_24h: number;
  volume_avg: number;
  volume_ratio: number;
  rsi: number;
  drawdown_from_ath: number;
  rally_from_30d_low: number;
  high_all_time: number;
  low_30d: number;
  ema20: number;
  ema50: number;
}

export interface CryptoScanResponse {
  scan_time: string;
  total: number;
  min_score: number;
  universe_size: number;
  results: CryptoResult[];
}

export interface CryptoChartResponse {
  ticker: string;
  chart: string;
  indicators: {
    current_price: number;
    sma20: number | null;
    sma50: number | null;
    sma200: number | null;
    rsi: number | null;
    macd: number | null;
    macd_signal: number | null;
    bb_upper: number | null;
    bb_lower: number | null;
    volume: number;
    volume_avg: number | null;
  };
  days: number;
  generated_at: string;
}

export interface SentimentBreakdown {
  score: number;
  max: number;
  value: string;
}

export interface CryptoSentiment {
  score: number | null;
  max_score: number;
  signal: 'VERY_BULLISH' | 'BULLISH' | 'NEUTRAL' | 'BEARISH' | 'VERY_BEARISH' | 'UNKNOWN';
  breakdown: Record<string, SentimentBreakdown>;
  data_completeness: number;
}

export interface CryptoSentimentResponse {
  ticker: string;
  name: string;
  symbol: string;
  sentiment: CryptoSentiment;
  social: {
    twitter_followers: number | null;
    reddit_subscribers: number | null;
    reddit_active_48h: number | null;
    telegram_users: number | null;
  };
  developer: {
    github_stars: number | null;
    github_forks: number | null;
    commits_4_weeks: number | null;
    contributors: number | null;
  };
  scores: {
    coingecko_rank: number | null;
    coingecko_score: number | null;
    community_score: number | null;
    developer_score: number | null;
    liquidity_score: number | null;
  };
  trending: boolean;
  price_changes: {
    '24h': number | null;
    '7d': number | null;
    '30d': number | null;
  };
  fetched_at: string;
}

export interface FearGreedIndex {
  value: number;
  classification: string;
  timestamp: string;
  date: string;
}

export interface FearGreedResponse {
  current: FearGreedIndex | null;
  history: FearGreedIndex[];
  fetched_at: string;
}

export interface CryptoFullAnalysis {
  ticker: string;
  name: string;
  chart: string;
  indicators: CryptoChartResponse['indicators'];
  signals: CryptoResult | null;
  sentiment: CryptoSentiment | null;
  social: CryptoSentimentResponse['social'] | null;
  developer: CryptoSentimentResponse['developer'] | null;
  scores: CryptoSentimentResponse['scores'] | null;
  trending: boolean;
  fear_greed: FearGreedIndex | null;
  generated_at: string;
}

// ─── Options Types ───────────────────────────────────────────────────

export interface OptionContract {
  symbol: string;
  strike: number;
  expiration: string;
  type: 'call' | 'put';
  bid: number;
  ask: number;
  mid: number;
  volume: number;
  open_interest: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}

export interface OptionsChain {
  ticker: string;
  underlying_price: number;
  expirations: string[];
  calls: OptionContract[];
  puts: OptionContract[];
  fetched_at: string;
}

export interface LeapsCandidate {
  ticker: string;
  name: string;
  current_price: number;
  strike: number;
  expiration: string;
  days_to_expiry: number;
  premium: number;
  delta: number;
  iv: number;
  iv_rank: number;
  leverage_ratio: number;
  breakeven: number;
  breakeven_pct: number;
  max_loss: number;
  score: number;
  flags: string[];
}

export interface LeapsScanResponse {
  scan_time: string;
  total: number;
  results: LeapsCandidate[];
}

export interface ZeroDteScore {
  ticker: string;
  score: number;
  max_score: number;
  direction: 'CALL' | 'PUT' | 'NEUTRAL';
  expected_range_pct: number;
  iv_percentile: number;
  volume_ratio: number;
  signals: string[];
  best_strike: number | null;
  best_premium: number | null;
  risk_reward: number | null;
}

export interface ZeroDteScanResponse {
  scan_time: string;
  total: number;
  results: ZeroDteScore[];
}

export interface CoveredCallResult {
  id: number;
  expiration: string;
  strike: string;
  premium: string;
  delta: string;
  iv: string;
  ivRank: number;
  otmPercent: string;
  annualizedReturn: string;
  maxProfit: string;
  breakeven: string;
}

export interface CoveredCallSearch {
  ticker: string;
  currentPrice: string;
  strategyInfo: {
    min: number;
    max: number;
    label: string;
    prob: string;
  };
  options: CoveredCallResult[];
}

export type CoveredCallStrategy = 'keep' | 'okay' | 'max';

export interface StrategyMatch {
  ticker: string;
  name: string;
  current_price: number;
  target_price: number;
  strategy: string;
  contracts: OptionContract[];
  max_profit: number;
  max_loss: number;
  breakeven: number;
  risk_reward: number;
  probability_of_profit: number;
  score: number;
}

export interface StrategyFinderResponse {
  scan_time: string;
  total: number;
  results: StrategyMatch[];
}

// ─── Signal Weights ──────────────────────────────────────────────────

export interface SignalWeight {
  name: string;
  weight: number;
  category: string;
  description?: string;
}

export interface WeightsResponse {
  weights: SignalWeight[];
  total_signals: number;
  categories: string[];
}
