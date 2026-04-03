import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { CoveredCallResult, CoveredCallSearch, CoveredCallStrategy } from '../types';

// ─── Mock data generator (replaced by live API when backend supports it) ─────

function generateMockOptions(
  ticker: string,
  strategy: CoveredCallStrategy,
): CoveredCallSearch {
  const basePrices: Record<string, number> = {
    AAPL: 195.5, NVDA: 875.25, TSLA: 248.75, MSFT: 420.1,
    AMZN: 185.3, GOOGL: 175.8, META: 505.25, SPY: 595.4,
    QQQ: 505.15, AMD: 162.4, PLTR: 68.9, COIN: 265.8,
  };
  const basePrice = basePrices[ticker.toUpperCase()] ?? Math.random() * 200 + 50;

  const deltaRanges: Record<CoveredCallStrategy, { min: number; max: number; label: string; prob: string }> = {
    keep: { min: 0.05, max: 0.15, label: 'Keep Shares', prob: '~90%' },
    okay: { min: 0.15, max: 0.30, label: 'Okay to Sell', prob: '~78%' },
    max: { min: 0.30, max: 0.50, label: 'Max Income', prob: '~60%' },
  };

  const range = deltaRanges[strategy];
  const expirations = ['Dec 13', 'Dec 20', 'Dec 27', 'Jan 3', 'Jan 10'];
  const options: CoveredCallResult[] = [];

  for (let i = 0; i < 5; i++) {
    const delta = range.min + Math.random() * (range.max - range.min);
    const otmPercent = 0.02 + 0.15 * (1 - delta);
    const strike = Math.round((basePrice * (1 + otmPercent)) / 0.5) * 0.5;
    const premium = basePrice * (0.005 + delta * 0.02) * (1 + i * 0.15);
    const iv = 25 + Math.random() * 40;
    const ivRank = Math.round(Math.random() * 100);

    options.push({
      id: i,
      expiration: expirations[i],
      strike: strike.toFixed(2),
      premium: premium.toFixed(2),
      delta: delta.toFixed(2),
      iv: iv.toFixed(1),
      ivRank,
      otmPercent: (otmPercent * 100).toFixed(1),
      annualizedReturn: ((premium / basePrice) * (52 / (i + 1)) * 100).toFixed(1),
      maxProfit: premium.toFixed(2),
      breakeven: (basePrice - premium).toFixed(2),
    });
  }

  return {
    ticker: ticker.toUpperCase(),
    currentPrice: basePrice.toFixed(2),
    strategyInfo: range,
    options,
  };
}

// ─── Constants ───────────────────────────────────────────────────────

const POPULAR_TICKERS = ['AAPL', 'NVDA', 'TSLA', 'MSFT', 'SPY', 'AMD', 'PLTR'];

interface StrategyDef {
  id: CoveredCallStrategy;
  label: string;
  delta: string;
  prob: string;
  color: string;
}

const STRATEGIES: StrategyDef[] = [
  { id: 'keep', label: 'Keep Shares', delta: '0.05-0.15', prob: '~90% keep', color: 'var(--accent-emerald)' },
  { id: 'okay', label: 'Okay to Sell', delta: '0.15-0.30', prob: '~78% keep', color: 'var(--accent-amber)' },
  { id: 'max', label: 'Max Income', delta: '0.30-0.50', prob: '~60% keep', color: 'var(--accent-rose)' },
];

// ─── Saved call type ─────────────────────────────────────────────────

interface SavedCall extends CoveredCallResult {
  ticker: string;
  savedAt: string;
  entryPrice: string;
}

// ─── Component ───────────────────────────────────────────────────────

export default function CoveredCallFinder() {
  const [ticker, setTicker] = useState('');
  const [strategy, setStrategy] = useState<CoveredCallStrategy | null>(null);
  const [results, setResults] = useState<CoveredCallSearch | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [recentSearches, setRecentSearches] = useState<string[]>(['NVDA', 'AAPL']);
  const [savedCalls, setSavedCalls] = useState<SavedCall[]>([]);
  const [activeView, setActiveView] = useState<'search' | 'saved'>('search');

  const handleSearch = () => {
    if (!ticker || !strategy) return;
    setIsLoading(true);

    // TODO: replace with live API call when backend supports it
    setTimeout(() => {
      const data = generateMockOptions(ticker, strategy);
      setResults(data);
      setIsLoading(false);

      if (!recentSearches.includes(ticker.toUpperCase())) {
        setRecentSearches((prev) => [ticker.toUpperCase(), ...prev].slice(0, 5));
      }
    }, 600);
  };

  const handleSave = (option: CoveredCallResult) => {
    if (!results) return;
    const saved: SavedCall = {
      ...option,
      ticker: results.ticker,
      savedAt: new Date().toISOString(),
      entryPrice: results.currentPrice,
    };
    setSavedCalls((prev) => [saved, ...prev]);
  };

  const isSaved = (option: CoveredCallResult): boolean =>
    savedCalls.some(
      (s) => s.ticker === results?.ticker && s.strike === option.strike && s.expiration === option.expiration,
    );

  return (
    <div>
      {/* View toggle */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setActiveView('search')}
          className={`flex-1 px-4 py-2.5 rounded-[var(--radius-md)] text-sm font-semibold transition-colors ${
            activeView === 'search'
              ? 'bg-[var(--accent-emerald)]/15 text-[var(--accent-emerald)] border border-[var(--accent-emerald)]/40'
              : 'bg-[var(--surface-700)]/50 text-gray-400 border border-transparent'
          }`}
        >
          Find Calls
        </button>
        <button
          onClick={() => setActiveView('saved')}
          className={`flex-1 px-4 py-2.5 rounded-[var(--radius-md)] text-sm font-semibold transition-colors ${
            activeView === 'saved'
              ? 'bg-[var(--accent-emerald)]/15 text-[var(--accent-emerald)] border border-[var(--accent-emerald)]/40'
              : 'bg-[var(--surface-700)]/50 text-gray-400 border border-transparent'
          }`}
        >
          Saved ({savedCalls.length})
        </button>
      </div>

      <AnimatePresence mode="wait">
        {activeView === 'search' ? (
          <motion.div
            key="search"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            {/* Search input */}
            <div className="mb-5">
              <div className="relative mb-3">
                <input
                  type="text"
                  placeholder="Enter ticker (e.g. AAPL)"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="w-full px-4 py-3 bg-[var(--surface-800)] border-2 border-[var(--surface-600)] rounded-[var(--radius-lg)] text-white font-mono text-lg uppercase tracking-widest focus:border-[var(--accent-emerald)] focus:outline-none"
                />
                {ticker && (
                  <button
                    onClick={() => setTicker('')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 w-7 h-7 flex items-center justify-center bg-[var(--surface-600)] rounded-[var(--radius-sm)] text-gray-400 text-sm hover:text-white"
                  >
                    x
                  </button>
                )}
              </div>

              {/* Quick picks */}
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <span className="text-xs text-gray-500 font-semibold uppercase tracking-wider">Popular:</span>
                {POPULAR_TICKERS.slice(0, 5).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTicker(t)}
                    className={`px-3 py-1 rounded-[var(--radius-sm)] text-xs font-mono font-semibold transition-colors ${
                      ticker === t
                        ? 'bg-[var(--accent-emerald)]/20 border border-[var(--accent-emerald)]/40 text-[var(--accent-emerald)]'
                        : 'bg-[var(--surface-700)]/60 border border-transparent text-gray-400 hover:text-gray-200'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              {recentSearches.length > 0 && (
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-gray-500 font-semibold uppercase tracking-wider">Recent:</span>
                  {recentSearches.map((t) => (
                    <button
                      key={t}
                      onClick={() => setTicker(t)}
                      className="px-3 py-1 bg-[var(--surface-700)]/60 rounded-[var(--radius-sm)] text-xs font-mono text-gray-400 hover:text-gray-200"
                    >
                      {t}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Strategy selection */}
            <div className="mb-5">
              <p className="text-sm text-gray-400 font-semibold mb-3">Choose your goal:</p>
              <div className="grid grid-cols-3 gap-3">
                {STRATEGIES.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setStrategy(s.id)}
                    className={`flex flex-col items-center gap-1.5 p-4 rounded-[var(--radius-lg)] border-2 transition-all ${
                      strategy === s.id
                        ? 'bg-[var(--surface-800)] border-current'
                        : 'bg-[var(--surface-800)]/60 border-[var(--surface-600)]/40 hover:border-[var(--surface-500)]'
                    }`}
                    style={{
                      color: strategy === s.id ? s.color : undefined,
                      boxShadow: strategy === s.id ? `0 0 20px color-mix(in srgb, ${s.color} 25%, transparent)` : undefined,
                    }}
                  >
                    <span className="text-sm font-semibold text-gray-200">{s.label}</span>
                    <span className="text-xs font-mono text-gray-500">delta {s.delta}</span>
                    <span
                      className="text-xs font-semibold"
                      style={{ color: s.color }}
                    >
                      {s.prob}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Search button */}
            <button
              onClick={handleSearch}
              disabled={!ticker || !strategy || isLoading}
              className={`w-full py-3.5 rounded-[var(--radius-lg)] text-base font-semibold transition-all mb-6 ${
                ticker && strategy && !isLoading
                  ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-lg shadow-emerald-900/30 hover:shadow-emerald-900/50'
                  : 'bg-[var(--surface-600)] text-gray-500 cursor-not-allowed'
              }`}
            >
              {isLoading ? (
                <span className="inline-block w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                'Find Best Calls'
              )}
            </button>

            {/* Results */}
            {results && !isLoading && (
              <div>
                <div className="flex items-center justify-between p-4 bg-[var(--surface-800)]/80 rounded-[var(--radius-lg)] border border-[var(--surface-600)]/40 mb-4">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl font-display font-bold text-[var(--accent-emerald)]">
                      {results.ticker}
                    </span>
                    <span className="text-lg font-mono text-gray-400">
                      ${results.currentPrice}
                    </span>
                  </div>
                  <span className="text-sm text-gray-400">
                    {results.strategyInfo.label}
                  </span>
                </div>

                <div className="space-y-3">
                  {results.options.map((opt, idx) => (
                    <motion.div
                      key={opt.id}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: idx * 0.08, duration: 0.3 }}
                      className="p-4 bg-[var(--surface-800)]/80 border border-[var(--surface-600)]/40 rounded-[var(--radius-lg)]"
                    >
                      {/* Top row: exp / strike / premium */}
                      <div className="grid grid-cols-3 gap-3 mb-3 pb-3 border-b border-[var(--surface-600)]/30">
                        <div>
                          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Exp</div>
                          <div className="text-sm font-semibold text-white">{opt.expiration}</div>
                        </div>
                        <div className="text-center">
                          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Strike</div>
                          <div className="text-base font-bold font-mono text-white">${opt.strike}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Premium</div>
                          <div className="text-base font-bold font-mono text-[var(--accent-emerald)]">${opt.premium}</div>
                        </div>
                      </div>

                      {/* Metrics row */}
                      <div className="flex justify-between mb-3 text-sm">
                        <span className="flex flex-col items-center font-mono text-gray-400">
                          <span className="text-[10px] text-gray-500">delta</span>
                          {opt.delta}
                        </span>
                        <span className="flex flex-col items-center font-mono text-gray-400">
                          <span className="text-[10px] text-gray-500">OTM</span>
                          {opt.otmPercent}%
                        </span>
                        <span className="flex flex-col items-center font-mono text-gray-400">
                          <span className="text-[10px] text-gray-500">IV</span>
                          {opt.iv}%
                        </span>
                        <span className="flex flex-col items-center px-2 py-1 bg-[var(--accent-emerald)]/10 rounded-[var(--radius-sm)]">
                          <span className="text-[10px] text-gray-500">Ann.</span>
                          <span className="font-mono font-semibold text-[var(--accent-emerald)]">{opt.annualizedReturn}%</span>
                        </span>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-500 font-mono">
                          Breakeven: ${opt.breakeven}
                        </span>
                        <button
                          onClick={() => !isSaved(opt) && handleSave(opt)}
                          disabled={isSaved(opt)}
                          className={`px-4 py-1.5 rounded-[var(--radius-md)] text-sm font-semibold transition-colors ${
                            isSaved(opt)
                              ? 'bg-[var(--accent-emerald)]/30 text-[var(--accent-emerald)] cursor-default'
                              : 'bg-[var(--accent-emerald)]/15 text-[var(--accent-emerald)] hover:bg-[var(--accent-emerald)]/25 border border-[var(--accent-emerald)]/30'
                          }`}
                        >
                          {isSaved(opt) ? 'Saved' : '+ Save'}
                        </button>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        ) : (
          /* ── Saved calls view ── */
          <motion.div
            key="saved"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            {savedCalls.length === 0 ? (
              <div className="text-center py-20">
                <p className="text-lg font-display text-gray-500 mb-1">No saved calls yet</p>
                <p className="text-sm text-gray-600">Save covered calls to track your picks</p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3 mb-5">
                  <div className="p-4 bg-[var(--surface-800)] border border-[var(--surface-600)]/40 rounded-[var(--radius-lg)] text-center">
                    <div className="text-2xl font-bold font-mono text-[var(--accent-emerald)]">
                      {savedCalls.length}
                    </div>
                    <div className="text-xs text-gray-500">Active</div>
                  </div>
                  <div className="p-4 bg-[var(--surface-800)] border border-[var(--surface-600)]/40 rounded-[var(--radius-lg)] text-center">
                    <div className="text-2xl font-bold font-mono text-[var(--accent-emerald)]">
                      ${savedCalls.reduce((sum, c) => sum + parseFloat(c.premium), 0).toFixed(2)}
                    </div>
                    <div className="text-xs text-gray-500">Total Premium</div>
                  </div>
                </div>

                <div className="space-y-3">
                  {savedCalls.map((call, idx) => (
                    <motion.div
                      key={idx}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="p-4 bg-[var(--surface-800)] border border-[var(--surface-600)]/40 rounded-[var(--radius-lg)]"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-display font-bold text-[var(--accent-emerald)]">
                          {call.ticker}
                        </span>
                        <span className="text-sm text-gray-400">{call.expiration}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm text-gray-500">
                        <span className="font-mono">${call.strike} strike</span>
                        <span className="font-mono text-[var(--accent-emerald)] font-semibold">
                          ${call.premium} premium
                        </span>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Disclaimer */}
      <div className="mt-10 pt-6 border-t border-[var(--surface-600)]/30 text-center">
        <p className="text-xs text-gray-600 leading-relaxed">
          Educational use only. Not investment advice. Options involve substantial risk of loss.
        </p>
      </div>
    </div>
  );
}
