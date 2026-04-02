import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  scanPatterns,
  getHighConfidence,
  analyzeStock,
  getWatchlist,
  addToWatchlist,
  removeFromWatchlist,
  getPerformance,
  scanCrypto,
  getCryptoFullAnalysis,
  getFearGreedIndex,
} from './api';
import type {
  PatternResult,
  WatchlistItem,
  AnalysisResponse,
  PerformanceResponse,
  CryptoResult,
  CryptoFullAnalysis,
  FearGreedResponse,
} from './types';

import StockCard from './components/StockCard';
import CryptoCard from './components/CryptoCard';
import WatchlistCard from './components/WatchlistCard';
import OptionsPanel from './components/OptionsPanel';
import CoveredCallFinder from './components/CoveredCallFinder';

// ─── Tab definitions ─────────────────────────────────────────────────

type Tab = 'scanner' | 'high-confidence' | 'watchlist' | 'crypto' | 'options' | 'covered-calls';

interface TabDef {
  id: Tab;
  label: string;
  color: string;
  activeClass: string;
}

const TABS: TabDef[] = [
  { id: 'scanner', label: 'Scanner', color: 'var(--accent-cyan)', activeClass: 'bg-[var(--accent-cyan)]/20 text-[var(--accent-cyan)] border-[var(--accent-cyan)]/40' },
  { id: 'high-confidence', label: 'High Conf.', color: 'var(--accent-emerald)', activeClass: 'bg-[var(--accent-emerald)]/20 text-[var(--accent-emerald)] border-[var(--accent-emerald)]/40' },
  { id: 'watchlist', label: 'Watchlist', color: 'var(--accent-violet)', activeClass: 'bg-[var(--accent-violet)]/20 text-[var(--accent-violet)] border-[var(--accent-violet)]/40' },
  { id: 'crypto', label: 'Crypto', color: 'var(--accent-amber)', activeClass: 'bg-[var(--accent-amber)]/20 text-[var(--accent-amber)] border-[var(--accent-amber)]/40' },
  { id: 'options', label: 'Options', color: 'var(--accent-violet)', activeClass: 'bg-[var(--accent-violet)]/20 text-[var(--accent-violet)] border-[var(--accent-violet)]/40' },
  { id: 'covered-calls', label: 'Covered Calls', color: 'var(--accent-emerald)', activeClass: 'bg-[var(--accent-emerald)]/20 text-[var(--accent-emerald)] border-[var(--accent-emerald)]/40' },
];

// ─── App ─────────────────────────────────────────────────────────────

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('scanner');
  const [results, setResults] = useState<PatternResult[]>([]);
  const [highConfidence, setHighConfidence] = useState<PatternResult[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [cryptoResults, setCryptoResults] = useState<CryptoResult[]>([]);
  const [fearGreed, setFearGreed] = useState<FearGreedResponse | null>(null);
  const [performance, setPerformance] = useState<PerformanceResponse | null>(null);
  const [selectedStock, setSelectedStock] = useState<AnalysisResponse | null>(null);
  const [selectedCrypto, setSelectedCrypto] = useState<CryptoFullAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [minScore, setMinScore] = useState(40);
  const [cryptoMinScore, setCryptoMinScore] = useState(20);

  useEffect(() => {
    if (activeTab === 'scanner') loadScan();
    else if (activeTab === 'high-confidence') loadHighConfidence();
    else if (activeTab === 'watchlist') loadWatchlist();
    else if (activeTab === 'crypto') loadCrypto();
  }, [activeTab]);

  // ── Data loaders ─────────────────────────────────────────────────

  const loadScan = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await scanPatterns(minScore);
      setResults(data.results);
    } catch {
      setError('Failed to load scan results. Is the backend running on port 8000?');
    }
    setLoading(false);
  };

  const loadHighConfidence = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getHighConfidence(70);
      setHighConfidence(data.results);
    } catch {
      setError('Failed to load high confidence plays.');
    }
    setLoading(false);
  };

  const loadWatchlist = async () => {
    setLoading(true);
    setError(null);
    try {
      const [watchData, perfData] = await Promise.all([getWatchlist(), getPerformance()]);
      setWatchlist(watchData.items);
      setPerformance(perfData);
    } catch {
      setError('Failed to load watchlist.');
    }
    setLoading(false);
  };

  const loadCrypto = async () => {
    setLoading(true);
    setError(null);
    try {
      const [cryptoData, fgData] = await Promise.all([
        scanCrypto(cryptoMinScore),
        getFearGreedIndex(),
      ]);
      setCryptoResults(cryptoData.results);
      setFearGreed(fgData);
    } catch {
      setError('Failed to load crypto scan. Is the backend running?');
    }
    setLoading(false);
  };

  // ── Handlers ─────────────────────────────────────────────────────

  const handleAnalyze = async (ticker: string) => {
    setLoading(true);
    try {
      const data = await analyzeStock(ticker);
      setSelectedStock(data);
    } catch {
      setError(`Failed to analyze ${ticker}`);
    }
    setLoading(false);
  };

  const handleAddToWatchlist = async (ticker: string) => {
    try {
      await addToWatchlist(ticker);
      alert(`Added ${ticker} to watchlist`);
      loadWatchlist();
    } catch (e: any) {
      alert(e.message || 'Failed to add');
    }
  };

  const handleRemoveFromWatchlist = async (ticker: string) => {
    if (confirm(`Remove ${ticker} from watchlist?`)) {
      try {
        await removeFromWatchlist(ticker);
        loadWatchlist();
      } catch {
        alert('Failed to remove');
      }
    }
  };

  const handleAnalyzeCrypto = async (ticker: string) => {
    setLoading(true);
    try {
      const data = await getCryptoFullAnalysis(ticker);
      setSelectedCrypto(data);
    } catch {
      setError(`Failed to analyze ${ticker}`);
    }
    setLoading(false);
  };

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div className="min-h-screen text-gray-200">
      {/* ── Header ── */}
      <header className="border-b border-[var(--surface-700)]/60 bg-[var(--surface-900)]/90 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h1 className="text-2xl font-display font-bold tracking-tight">
                <span className="bg-gradient-to-r from-[var(--accent-emerald)] via-[var(--accent-cyan)] to-[var(--accent-emerald)] bg-clip-text text-transparent">
                  Quantum Alpha Hunter
                </span>
              </h1>
              <p className="text-xs text-gray-500 tracking-wide">
                Equities &middot; Crypto &middot; Options &middot; Covered Calls
              </p>
            </div>
          </div>

          {/* Tab bar */}
          <div className="flex gap-1.5 overflow-x-auto pb-1 -mb-px">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`px-3 py-1.5 rounded-[var(--radius-md)] text-sm font-semibold whitespace-nowrap transition-colors border ${
                  activeTab === t.id
                    ? t.activeClass
                    : 'bg-transparent text-gray-500 border-transparent hover:text-gray-300 hover:bg-[var(--surface-800)]'
                }`}
              >
                {t.label}
                {t.id === 'watchlist' && watchlist.length > 0 && (
                  <span className="ml-1 text-xs opacity-70">({watchlist.length})</span>
                )}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6">
        {/* Error */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-4 p-3 bg-red-900/40 border border-red-500/50 rounded-[var(--radius-md)] text-red-300 text-sm"
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Loading spinner */}
        {loading && (
          <div className="flex items-center justify-center py-16">
            <div className="w-10 h-10 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {/* ── Scanner Tab ── */}
        {activeTab === 'scanner' && !loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
          >
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <label className="text-sm text-gray-500">Min Score:</label>
                <input
                  type="number"
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  className="w-20 px-3 py-2 bg-[var(--surface-800)] border border-[var(--surface-600)] rounded-[var(--radius-md)] text-white font-mono text-sm focus:border-[var(--accent-cyan)] focus:outline-none"
                />
                <button
                  onClick={loadScan}
                  className="px-4 py-2 bg-[var(--accent-cyan)]/20 hover:bg-[var(--accent-cyan)]/30 text-[var(--accent-cyan)] rounded-[var(--radius-md)] text-sm font-semibold transition-colors"
                >
                  Refresh
                </button>
              </div>
              <span className="text-sm text-gray-500 font-mono">{results.length} found</span>
            </div>

            <div className="grid gap-4">
              {results.map((r) => (
                <StockCard
                  key={r.ticker}
                  result={r}
                  onAnalyze={handleAnalyze}
                  onAddToWatchlist={handleAddToWatchlist}
                />
              ))}
            </div>
          </motion.div>
        )}

        {/* ── High Confidence Tab ── */}
        {activeTab === 'high-confidence' && !loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
          >
            <div className="mb-6 p-4 bg-gradient-to-r from-emerald-900/20 to-cyan-900/20 border border-[var(--accent-emerald)]/20 rounded-[var(--radius-lg)]">
              <h2 className="text-base font-display font-bold text-[var(--accent-emerald)] mb-2">
                High Confidence Criteria
              </h2>
              <ul className="text-sm text-gray-400 list-disc list-inside space-y-1">
                <li>Pattern Score &gt;= 70</li>
                <li>Stage: EARLY or MID (not extended)</li>
                <li>3+ bullish signals (EMA stack, MACD, RSI thrust, volume, momentum)</li>
                <li>Analyst upside &gt; 30% (bonus)</li>
              </ul>
            </div>

            <div className="grid gap-4">
              {highConfidence.map((r) => (
                <StockCard
                  key={r.ticker}
                  result={r}
                  onAnalyze={handleAnalyze}
                  onAddToWatchlist={handleAddToWatchlist}
                  isHighConfidence
                />
              ))}
              {highConfidence.length === 0 && (
                <div className="text-center py-16 text-gray-500">
                  No high confidence plays found at this time.
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* ── Watchlist Tab ── */}
        {activeTab === 'watchlist' && !loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
          >
            {/* Performance summary */}
            {performance && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                {[
                  { label: 'Active', value: performance.active_positions, color: '' },
                  {
                    label: `Win Rate (${performance.winners}W / ${performance.losers}L)`,
                    value: `${performance.win_rate}%`,
                    color: performance.win_rate >= 50 ? 'text-[var(--accent-emerald)]' : 'text-[var(--accent-rose)]',
                  },
                  {
                    label: 'Avg P&L',
                    value: `${performance.avg_pnl_pct >= 0 ? '+' : ''}${performance.avg_pnl_pct}%`,
                    color: performance.avg_pnl_pct >= 0 ? 'text-[var(--accent-emerald)]' : 'text-[var(--accent-rose)]',
                  },
                  {
                    label: 'Total P&L',
                    value: `${performance.total_pnl_pct >= 0 ? '+' : ''}${performance.total_pnl_pct}%`,
                    color: performance.total_pnl_pct >= 0 ? 'text-[var(--accent-emerald)]' : 'text-[var(--accent-rose)]',
                  },
                ].map((s, i) => (
                  <div
                    key={i}
                    className="p-4 bg-[var(--surface-800)]/70 rounded-[var(--radius-lg)] border border-[var(--surface-600)]/40"
                  >
                    <div className={`text-2xl font-bold font-mono ${s.color}`}>{s.value}</div>
                    <div className="text-xs text-gray-500">{s.label}</div>
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-3">
              {watchlist.map((item) => (
                <WatchlistCard
                  key={item.ticker}
                  item={item}
                  onAnalyze={handleAnalyze}
                  onRemove={handleRemoveFromWatchlist}
                />
              ))}
              {watchlist.length === 0 && (
                <div className="text-center py-16 text-gray-500">
                  <p className="mb-1 font-display">Your watchlist is empty.</p>
                  <p className="text-sm">Add stocks from the Scanner or High Confidence tabs.</p>
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* ── Crypto Tab ── */}
        {activeTab === 'crypto' && !loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
          >
            {/* Fear & Greed mini-chart */}
            {fearGreed?.current && (
              <div className="mb-6 p-4 bg-[var(--surface-800)]/70 rounded-[var(--radius-xl)] border border-[var(--surface-600)]/40">
                <div className="flex items-start gap-6">
                  <div className="shrink-0 min-w-[120px]">
                    <div className="text-xs text-gray-500 uppercase tracking-wider mb-2">Market Sentiment</div>
                    <div
                      className={`text-5xl font-bold font-mono mb-1 ${
                        fearGreed.current.value >= 75
                          ? 'text-[var(--accent-emerald)]'
                          : fearGreed.current.value >= 55
                            ? 'text-lime-400'
                            : fearGreed.current.value >= 45
                              ? 'text-[var(--accent-amber)]'
                              : fearGreed.current.value >= 25
                                ? 'text-orange-400'
                                : 'text-[var(--accent-rose)]'
                      }`}
                    >
                      {fearGreed.current.value}
                    </div>
                    <span
                      className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${
                        fearGreed.current.classification === 'Extreme Greed'
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : fearGreed.current.classification === 'Greed'
                            ? 'bg-lime-500/20 text-lime-400'
                            : fearGreed.current.classification === 'Neutral'
                              ? 'bg-amber-500/20 text-amber-400'
                              : fearGreed.current.classification === 'Fear'
                                ? 'bg-orange-500/20 text-orange-400'
                                : 'bg-red-500/20 text-red-400'
                      }`}
                    >
                      {fearGreed.current.classification}
                    </span>
                  </div>

                  {/* 6-month sparkline */}
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-gray-500 mb-2">Fear &amp; Greed -- 6 Month History</div>
                    <div className="flex items-stretch h-28">
                      <div className="flex flex-col justify-between text-[10px] pr-2 w-8 font-mono">
                        <span className="text-[var(--accent-emerald)]">100</span>
                        <span className="text-gray-600">50</span>
                        <span className="text-[var(--accent-rose)]">0</span>
                      </div>

                      <div className="flex-1 relative bg-[var(--surface-950)]/60 rounded overflow-hidden">
                        <div className="absolute inset-0 flex flex-col">
                          <div className="flex-1 bg-emerald-500/5 border-b border-emerald-500/20" />
                          <div className="flex-1 bg-amber-500/5 border-b border-[var(--surface-600)]/30" />
                          <div className="flex-1 bg-red-500/5" />
                        </div>

                        <svg
                          className="absolute inset-0 w-full h-full"
                          viewBox="0 0 360 100"
                          preserveAspectRatio="none"
                        >
                          <line x1="0" y1="25" x2="360" y2="25" stroke="#374151" strokeWidth="0.5" strokeDasharray="2,4" />
                          <line x1="0" y1="50" x2="360" y2="50" stroke="#4b5563" strokeWidth="1" />
                          <line x1="0" y1="75" x2="360" y2="75" stroke="#374151" strokeWidth="0.5" strokeDasharray="2,4" />

                          <defs>
                            <linearGradient id="fgAreaGradient" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="var(--accent-amber)" stopOpacity="0.4" />
                              <stop offset="100%" stopColor="var(--accent-amber)" stopOpacity="0.05" />
                            </linearGradient>
                          </defs>

                          {(() => {
                            const data = fearGreed.history.slice(0, 180).reverse();
                            const len = data.length;
                            if (len === 0) return null;

                            const points = data
                              .map((h, i) => {
                                const x = (i / (len - 1)) * 360;
                                const y = 100 - h.value;
                                return `${x},${y}`;
                              })
                              .join(' ');

                            const firstY = 100 - data[0].value;
                            const lastY = 100 - data[len - 1].value;
                            const areaPoints = `0,100 0,${firstY} ${points} 360,${lastY} 360,100`;

                            return (
                              <>
                                <polygon points={areaPoints} fill="url(#fgAreaGradient)" />
                                <polyline
                                  points={points}
                                  fill="none"
                                  stroke="var(--accent-amber)"
                                  strokeWidth="1.5"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  vectorEffect="non-scaling-stroke"
                                />
                              </>
                            );
                          })()}
                        </svg>

                        <div className="absolute right-2 top-1 text-[9px] text-emerald-400/60 font-semibold">
                          GREED
                        </div>
                        <div className="absolute right-2 bottom-1 text-[9px] text-red-400/60 font-semibold">
                          FEAR
                        </div>
                      </div>
                    </div>

                    <div className="flex justify-between text-[10px] text-gray-600 mt-1 ml-8 font-mono">
                      <span>6 months ago</span>
                      <span>3 months ago</span>
                      <span>Today</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <label className="text-sm text-gray-500">Min Score:</label>
                <input
                  type="number"
                  value={cryptoMinScore}
                  onChange={(e) => setCryptoMinScore(Number(e.target.value))}
                  className="w-20 px-3 py-2 bg-[var(--surface-800)] border border-[var(--surface-600)] rounded-[var(--radius-md)] text-white font-mono text-sm focus:border-[var(--accent-amber)] focus:outline-none"
                />
                <button
                  onClick={loadCrypto}
                  className="px-4 py-2 bg-[var(--accent-amber)]/20 hover:bg-[var(--accent-amber)]/30 text-[var(--accent-amber)] rounded-[var(--radius-md)] text-sm font-semibold transition-colors"
                >
                  Refresh
                </button>
              </div>
              <span className="text-sm text-gray-500 font-mono">{cryptoResults.length} found</span>
            </div>

            <div className="grid gap-4">
              {cryptoResults.map((c) => (
                <CryptoCard key={c.ticker} crypto={c} onAnalyze={handleAnalyzeCrypto} />
              ))}
              {cryptoResults.length === 0 && (
                <div className="text-center py-16 text-gray-500">
                  No crypto matches found. Try lowering the minimum score.
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* ── Options Tab ── */}
        {activeTab === 'options' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
          >
            <OptionsPanel />
          </motion.div>
        )}

        {/* ── Covered Calls Tab ── */}
        {activeTab === 'covered-calls' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
          >
            <div className="mb-6">
              <h2 className="text-xl font-display font-bold text-white tracking-tight">
                Covered Call Finder
              </h2>
              <p className="text-sm text-gray-500">
                Turn your shares into weekly income -- find the best strikes for your risk tolerance
              </p>
            </div>
            <CoveredCallFinder />
          </motion.div>
        )}
      </main>

      {/* ── Stock Analysis Modal ── */}
      <AnimatePresence>
        {selectedStock && (
          <AnalysisModal
            data={selectedStock}
            onClose={() => setSelectedStock(null)}
            onAddToWatchlist={handleAddToWatchlist}
          />
        )}
      </AnimatePresence>

      {/* ── Crypto Analysis Modal ── */}
      <AnimatePresence>
        {selectedCrypto && (
          <CryptoModal data={selectedCrypto} onClose={() => setSelectedCrypto(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Analysis Modal ──────────────────────────────────────────────────

interface AnalysisModalProps {
  data: AnalysisResponse;
  onClose: () => void;
  onAddToWatchlist: (ticker: string) => void;
}

function AnalysisModal({ data, onClose, onAddToWatchlist }: AnalysisModalProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="bg-[var(--surface-900)] border border-[var(--surface-600)]/40 rounded-[var(--radius-xl)] max-w-5xl w-full max-h-[90vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-display font-bold text-white">{data.ticker} Analysis</h2>
            <button
              onClick={onClose}
              className="p-2 hover:bg-[var(--surface-700)] rounded-[var(--radius-md)] transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Chart */}
          <div className="mb-6 rounded-[var(--radius-lg)] overflow-hidden">
            <img
              src={`data:image/png;base64,${data.chart}`}
              alt={`${data.ticker} Chart`}
              className="w-full"
            />
          </div>

          {/* Key levels + pattern data */}
          <div className="grid md:grid-cols-2 gap-6">
            <div className="bg-[var(--surface-800)]/60 rounded-[var(--radius-lg)] p-4">
              <h3 className="text-base font-display font-bold text-[var(--accent-emerald)] mb-3">
                Key Resistance Levels
              </h3>
              <div className="space-y-2">
                {data.analysis.key_levels.map((lvl, i) => (
                  <div key={i} className="flex items-center justify-between text-sm font-mono">
                    <span>R{i + 1}: ${lvl.level}</span>
                    <span className="text-gray-500">+{lvl.pct_above}%</span>
                    <span className="text-[var(--accent-amber)]">
                      {'*'.repeat(Math.min(lvl.strength, 5))} ({lvl.strength}x)
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {data.pattern && (
              <div className="bg-[var(--surface-800)]/60 rounded-[var(--radius-lg)] p-4">
                <h3 className="text-base font-display font-bold text-[var(--accent-cyan)] mb-3">
                  Pattern Data
                </h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    Score: <span className="text-[var(--accent-emerald)] font-mono">{data.pattern.score}</span>
                  </div>
                  <div>
                    Stage: <span className="text-[var(--accent-amber)] font-mono">{data.pattern.stage}</span>
                  </div>
                  <div>
                    Drawdown: <span className="text-[var(--accent-rose)] font-mono">{data.pattern.drawdown}%</span>
                  </div>
                  <div>
                    Rally: <span className="text-[var(--accent-emerald)] font-mono">+{data.pattern.rally_from_low}%</span>
                  </div>
                  <div>RSI: <span className="font-mono">{data.pattern.rsi}</span></div>
                  <div>Vol Exp: <span className="font-mono">{data.pattern.vol_expansion}x</span></div>
                  <div>EMA Stack: {data.pattern.ema_bullish ? 'Yes' : 'No'}</div>
                  <div>MACD Bull: {data.pattern.macd_bullish ? 'Yes' : 'No'}</div>
                </div>

                <div className="mt-4 pt-4 border-t border-[var(--surface-600)]/40 text-sm font-mono space-y-1">
                  <div>
                    Stop: <span className="text-[var(--accent-rose)]">${data.pattern.stop}</span>
                  </div>
                  <div>
                    T1 (+2R): <span className="text-[var(--accent-emerald)]">${data.pattern.t1}</span>
                  </div>
                  <div>
                    T2 (+4R): <span className="text-[var(--accent-emerald)]">${data.pattern.t2}</span>
                  </div>
                  <div>
                    +10R: <span className="text-[var(--accent-amber)]">${data.pattern.t4} (+{data.pattern.pct_to_10r}%)</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="mt-6 flex gap-3 justify-end">
            <button
              onClick={() => onAddToWatchlist(data.ticker)}
              className="px-4 py-2 bg-[var(--accent-emerald)]/20 hover:bg-[var(--accent-emerald)]/30 text-[var(--accent-emerald)] rounded-[var(--radius-md)] font-semibold transition-colors"
            >
              Add to Watchlist
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-[var(--surface-700)] hover:bg-[var(--surface-600)] rounded-[var(--radius-md)] font-semibold transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ─── Crypto Modal ────────────────────────────────────────────────────

interface CryptoModalProps {
  data: CryptoFullAnalysis;
  onClose: () => void;
}

function CryptoModal({ data, onClose }: CryptoModalProps) {
  const formatNumber = (num: number | null | undefined) => {
    if (num === null || num === undefined) return 'N/A';
    if (num >= 1e9) return `${(num / 1e9).toFixed(1)}B`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(1)}M`;
    if (num >= 1e3) return `${(num / 1e3).toFixed(1)}K`;
    return num.toLocaleString();
  };

  const sentimentBg = (signal: string) => {
    switch (signal) {
      case 'VERY_BULLISH': return 'bg-emerald-600';
      case 'BULLISH': return 'bg-lime-600';
      case 'NEUTRAL': return 'bg-amber-600';
      case 'BEARISH': return 'bg-orange-600';
      case 'VERY_BEARISH': return 'bg-red-600';
      default: return 'bg-gray-600';
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="bg-[var(--surface-900)] border border-[var(--surface-600)]/40 rounded-[var(--radius-xl)] max-w-6xl w-full max-h-[95vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4">
              <h2 className="text-2xl font-display font-bold">{data.ticker.replace('-USD', '')}</h2>
              <span className="text-lg text-gray-400">{data.name}</span>
              {data.trending && (
                <span className="px-2 py-1 bg-[var(--accent-amber)] text-black rounded-[var(--radius-sm)] text-xs font-bold">
                  TRENDING
                </span>
              )}
            </div>
            <button onClick={onClose} className="p-2 hover:bg-[var(--surface-700)] rounded-[var(--radius-md)] transition-colors">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Price + Fear/Greed */}
          <div className="flex items-center gap-6 mb-4">
            <div className="text-3xl font-bold font-mono text-[var(--accent-amber)]">
              ${data.indicators?.current_price?.toLocaleString()}
            </div>
            {data.fear_greed && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-500">Market:</span>
                <span
                  className={`px-2 py-1 rounded-[var(--radius-sm)] text-sm font-medium ${
                    data.fear_greed.value >= 55
                      ? 'bg-emerald-600/50'
                      : data.fear_greed.value >= 45
                        ? 'bg-amber-600/50'
                        : 'bg-red-600/50'
                  }`}
                >
                  {data.fear_greed.classification} ({data.fear_greed.value})
                </span>
              </div>
            )}
          </div>

          {/* Chart */}
          {data.chart && (
            <div className="mb-6 rounded-[var(--radius-lg)] overflow-hidden border border-[var(--surface-600)]/40">
              <img
                src={`data:image/png;base64,${data.chart}`}
                alt={`${data.ticker} Chart`}
                className="w-full"
              />
            </div>
          )}

          {/* Two-column layout */}
          <div className="grid md:grid-cols-2 gap-6">
            {/* Left: Sentiment */}
            <div className="space-y-4">
              {data.sentiment && (
                <div className="p-4 bg-[var(--surface-800)]/60 rounded-[var(--radius-lg)]">
                  <h3 className="text-base font-display font-bold text-[var(--accent-violet)] mb-3">
                    Social Sentiment
                  </h3>
                  <div className="flex items-center gap-4 mb-4">
                    <div className="text-4xl font-bold font-mono text-white">
                      {data.sentiment.score?.toFixed(0) || 'N/A'}
                    </div>
                    <div>
                      <span
                        className={`px-3 py-1 rounded-[var(--radius-md)] text-sm font-semibold ${sentimentBg(data.sentiment.signal)}`}
                      >
                        {data.sentiment.signal.replace('_', ' ')}
                      </span>
                      <div className="text-xs text-gray-500 mt-1">
                        {data.sentiment.data_completeness}% data coverage
                      </div>
                    </div>
                  </div>

                  {data.sentiment.breakdown &&
                    Object.keys(data.sentiment.breakdown).length > 0 && (
                      <div className="space-y-2">
                        {Object.entries(data.sentiment.breakdown).map(([key, val]) => (
                          <div key={key} className="flex items-center justify-between text-sm">
                            <span className="text-gray-400">{key.replace(/_/g, ' ')}</span>
                            <div className="flex items-center gap-2">
                              <div className="w-24 h-2 bg-[var(--surface-700)] rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-[var(--accent-violet)]"
                                  style={{ width: `${(val.score / val.max) * 100}%` }}
                                />
                              </div>
                              <span className="text-[var(--accent-violet)] w-12 text-right font-mono">
                                {val.score}/{val.max}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                </div>
              )}

              {data.social && (
                <div className="p-4 bg-[var(--surface-800)]/60 rounded-[var(--radius-lg)]">
                  <h3 className="text-base font-display font-bold text-[var(--accent-cyan)] mb-3">
                    Social Metrics
                  </h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    {[
                      { label: 'Twitter Followers', val: data.social.twitter_followers, color: 'text-[var(--accent-cyan)]' },
                      { label: 'Reddit Subs', val: data.social.reddit_subscribers, color: 'text-[var(--accent-amber)]' },
                      { label: 'Reddit Active (48h)', val: data.social.reddit_active_48h, color: 'text-orange-300' },
                      { label: 'Telegram Users', val: data.social.telegram_users, color: 'text-cyan-400' },
                    ].map((m) => (
                      <div key={m.label}>
                        <div className="text-gray-500">{m.label}</div>
                        <div className={`text-xl font-semibold font-mono ${m.color}`}>
                          {formatNumber(m.val)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {data.developer && (
                <div className="p-4 bg-[var(--surface-800)]/60 rounded-[var(--radius-lg)]">
                  <h3 className="text-base font-display font-bold text-[var(--accent-emerald)] mb-3">
                    Developer Activity
                  </h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    {[
                      { label: 'GitHub Stars', val: data.developer.github_stars },
                      { label: 'GitHub Forks', val: data.developer.github_forks },
                      { label: 'Commits (4 wks)', val: data.developer.commits_4_weeks, color: 'text-[var(--accent-emerald)]' },
                      { label: 'Contributors', val: data.developer.contributors },
                    ].map((m) => (
                      <div key={m.label}>
                        <div className="text-gray-500">{m.label}</div>
                        <div className={`text-xl font-semibold font-mono ${m.color ?? 'text-white'}`}>
                          {formatNumber(m.val)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Right: Technical */}
            <div className="space-y-4">
              {data.signals && (
                <div className="p-4 bg-[var(--surface-800)]/60 rounded-[var(--radius-lg)]">
                  <h3 className="text-base font-display font-bold text-[var(--accent-amber)] mb-3">
                    Technical Signals
                  </h3>
                  <div className="flex items-center gap-4 mb-4">
                    <div className="text-4xl font-bold font-mono text-[var(--accent-amber)]">
                      {data.signals.score}
                    </div>
                    <div>
                      <span
                        className={`px-3 py-1 rounded-[var(--radius-md)] text-sm font-semibold ${
                          data.signals.trend === 'BULLISH'
                            ? 'bg-emerald-600'
                            : data.signals.trend === 'RECOVERING'
                              ? 'bg-amber-600'
                              : data.signals.trend === 'BEARISH'
                                ? 'bg-red-600'
                                : 'bg-gray-600'
                        }`}
                      >
                        {data.signals.trend}
                      </span>
                      <div className="text-xs text-gray-500 mt-1">
                        {data.signals.signals_triggered} signals fired
                      </div>
                    </div>
                  </div>

                  {data.signals.flags && data.signals.flags.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-4">
                      {data.signals.flags.map((flag, i) => (
                        <span
                          key={i}
                          className="px-2 py-1 bg-[var(--accent-amber)]/15 rounded-[var(--radius-sm)] text-xs text-[var(--accent-amber)]"
                        >
                          {flag}
                        </span>
                      ))}
                    </div>
                  )}

                  {data.signals.signal_breakdown && (
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {Object.entries(data.signals.signal_breakdown)
                        .sort(([, a], [, b]) => Math.abs(b as number) - Math.abs(a as number))
                        .map(([signal, weight]) => (
                          <div
                            key={signal}
                            className="flex items-center justify-between p-1.5 bg-[var(--surface-700)]/40 rounded-[var(--radius-sm)] text-sm"
                          >
                            <span className="text-gray-300">{signal.replace(/_/g, ' ')}</span>
                            <span
                              className={`font-medium font-mono ${
                                (weight as number) >= 0
                                  ? 'text-[var(--accent-emerald)]'
                                  : 'text-[var(--accent-rose)]'
                              }`}
                            >
                              {(weight as number) >= 0 ? '+' : ''}
                              {weight}
                            </span>
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              )}

              {data.scores && (
                <div className="p-4 bg-[var(--surface-800)]/60 rounded-[var(--radius-lg)]">
                  <h3 className="text-base font-display font-bold text-[var(--accent-amber)] mb-3">
                    CoinGecko Scores
                  </h3>
                  <div className="space-y-3">
                    {data.scores.coingecko_rank && (
                      <div className="flex justify-between">
                        <span className="text-gray-400">Rank</span>
                        <span className="font-semibold font-mono">#{data.scores.coingecko_rank}</span>
                      </div>
                    )}
                    {(
                      [
                        ['Community', data.scores.community_score],
                        ['Developer', data.scores.developer_score],
                        ['Liquidity', data.scores.liquidity_score],
                      ] as [string, number | null][]
                    ).map(
                      ([label, score]) =>
                        score && (
                          <div key={label}>
                            <div className="flex justify-between text-sm mb-1">
                              <span className="text-gray-400">{label}</span>
                              <span className="font-mono">{score.toFixed(1)}/100</span>
                            </div>
                            <div className="w-full h-2 bg-[var(--surface-700)] rounded-full overflow-hidden">
                              <div
                                className="h-full bg-[var(--accent-amber)]"
                                style={{ width: `${score}%` }}
                              />
                            </div>
                          </div>
                        ),
                    )}
                  </div>
                </div>
              )}

              {data.indicators && (
                <div className="p-4 bg-[var(--surface-800)]/60 rounded-[var(--radius-lg)]">
                  <h3 className="text-base font-display font-bold text-[var(--accent-cyan)] mb-3">
                    Technical Indicators
                  </h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <span className="text-gray-500">RSI:</span>
                      <span
                        className={`ml-2 font-medium font-mono ${
                          data.indicators.rsi && data.indicators.rsi > 70
                            ? 'text-[var(--accent-rose)]'
                            : data.indicators.rsi && data.indicators.rsi < 30
                              ? 'text-[var(--accent-emerald)]'
                              : 'text-[var(--accent-amber)]'
                        }`}
                      >
                        {data.indicators.rsi?.toFixed(1) || 'N/A'}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">MACD:</span>
                      <span
                        className={`ml-2 font-medium font-mono ${
                          data.indicators.macd && data.indicators.macd > 0
                            ? 'text-[var(--accent-emerald)]'
                            : 'text-[var(--accent-rose)]'
                        }`}
                      >
                        {data.indicators.macd?.toFixed(2) || 'N/A'}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">SMA20:</span>
                      <span className="ml-2 font-mono">${data.indicators.sma20?.toLocaleString() || 'N/A'}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">SMA50:</span>
                      <span className="ml-2 font-mono">${data.indicators.sma50?.toLocaleString() || 'N/A'}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">BB Upper:</span>
                      <span className="ml-2 font-mono">${data.indicators.bb_upper?.toLocaleString() || 'N/A'}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">BB Lower:</span>
                      <span className="ml-2 font-mono">${data.indicators.bb_lower?.toLocaleString() || 'N/A'}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Close */}
          <div className="mt-6 flex justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-[var(--surface-700)] hover:bg-[var(--surface-600)] rounded-[var(--radius-md)] font-semibold transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

export default App;
