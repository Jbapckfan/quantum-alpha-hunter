import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { scanZeroDte, scanLeaps, findStrategies } from '../api';
import type { ZeroDteScore, LeapsCandidate, StrategyMatch } from '../types';

type SubTab = '0dte' | 'leaps' | 'strategies';

export default function OptionsPanel() {
  const [subTab, setSubTab] = useState<SubTab>('0dte');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 0DTE state
  const [zdteResults, setZdteResults] = useState<ZeroDteScore[]>([]);

  // LEAPS state
  const [leapsResults, setLeapsResults] = useState<LeapsCandidate[]>([]);

  // Strategy finder state
  const [stratTicker, setStratTicker] = useState('');
  const [stratTarget, setStratTarget] = useState('');
  const [stratResults, setStratResults] = useState<StrategyMatch[]>([]);

  const loadZeroDte = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await scanZeroDte();
      setZdteResults(data.results);
    } catch (e: any) {
      setError(e.message ?? 'Failed to load 0DTE scores');
    }
    setLoading(false);
  };

  const loadLeaps = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await scanLeaps();
      setLeapsResults(data.results);
    } catch (e: any) {
      setError(e.message ?? 'Failed to load LEAPS');
    }
    setLoading(false);
  };

  const loadStrategies = async () => {
    if (!stratTicker || !stratTarget) return;
    setLoading(true);
    setError(null);
    try {
      const data = await findStrategies(stratTicker.toUpperCase(), parseFloat(stratTarget));
      setStratResults(data.results);
    } catch (e: any) {
      setError(e.message ?? 'Strategy search failed');
    }
    setLoading(false);
  };

  const dirColor = (dir: string) =>
    dir === 'CALL'
      ? 'text-[var(--accent-emerald)]'
      : dir === 'PUT'
        ? 'text-[var(--accent-rose)]'
        : 'text-gray-400';

  const tabs: { id: SubTab; label: string }[] = [
    { id: '0dte', label: '0DTE Scanner' },
    { id: 'leaps', label: 'LEAPS' },
    { id: 'strategies', label: 'Strategy Finder' },
  ];

  return (
    <div>
      {/* Sub-tabs */}
      <div className="flex gap-2 mb-6">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setSubTab(t.id)}
            className={`px-4 py-2 rounded-[var(--radius-md)] text-sm font-semibold transition-colors ${
              subTab === t.id
                ? 'bg-[var(--accent-violet)]/20 text-[var(--accent-violet)] border border-[var(--accent-violet)]/40'
                : 'bg-[var(--surface-700)]/50 text-gray-400 border border-transparent hover:bg-[var(--surface-700)]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/40 border border-red-500/50 rounded-[var(--radius-md)] text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="w-10 h-10 border-2 border-[var(--accent-violet)] border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      <AnimatePresence mode="wait">
        {/* ── 0DTE Tab ── */}
        {subTab === '0dte' && !loading && (
          <motion.div
            key="0dte"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="text-lg font-display font-bold text-white">0DTE Opportunities</h3>
                <p className="text-sm text-gray-500">Same-day expiration plays ranked by edge</p>
              </div>
              <button
                onClick={loadZeroDte}
                className="px-4 py-2 bg-[var(--accent-violet)]/20 hover:bg-[var(--accent-violet)]/30 text-[var(--accent-violet)] rounded-[var(--radius-md)] text-sm font-semibold transition-colors"
              >
                Scan Now
              </button>
            </div>

            {zdteResults.length === 0 ? (
              <div className="text-center py-16 text-gray-500">
                <p className="text-lg mb-1 font-display">No 0DTE data yet</p>
                <p className="text-sm">Hit "Scan Now" to find same-day plays</p>
              </div>
            ) : (
              <div className="grid gap-3">
                {zdteResults.map((z) => (
                  <motion.div
                    key={z.ticker}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-4 bg-[var(--surface-800)]/70 border border-[var(--surface-600)]/40 rounded-[var(--radius-lg)]"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className="text-lg font-display font-bold text-white">{z.ticker}</span>
                        <span className={`text-sm font-semibold font-mono ${dirColor(z.direction)}`}>
                          {z.direction}
                        </span>
                        <span className={`px-2 py-0.5 rounded-[var(--radius-sm)] text-xs font-semibold ${
                          z.score >= 70 ? 'bg-emerald-600' : z.score >= 50 ? 'bg-amber-600' : 'bg-gray-600'
                        } text-white`}>
                          {z.score}/{z.max_score}
                        </span>
                      </div>
                      {z.risk_reward && (
                        <span className="text-sm font-mono text-[var(--accent-cyan)]">
                          R:R {z.risk_reward.toFixed(1)}
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-2">
                      <div>
                        <span className="text-gray-500">Exp Range:</span>
                        <span className="ml-2 font-mono text-white">{z.expected_range_pct.toFixed(2)}%</span>
                      </div>
                      <div>
                        <span className="text-gray-500">IV %ile:</span>
                        <span className="ml-2 font-mono text-[var(--accent-amber)]">{z.iv_percentile}%</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Vol Ratio:</span>
                        <span className="ml-2 font-mono text-[var(--accent-cyan)]">{z.volume_ratio.toFixed(1)}x</span>
                      </div>
                      {z.best_strike && (
                        <div>
                          <span className="text-gray-500">Strike:</span>
                          <span className="ml-2 font-mono text-white">${z.best_strike}</span>
                          {z.best_premium && (
                            <span className="ml-1 text-[var(--accent-emerald)]">(${z.best_premium})</span>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      {z.signals.map((s, i) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 bg-[var(--accent-violet)]/15 rounded-[var(--radius-sm)] text-xs text-[var(--accent-violet)]"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </motion.div>
        )}

        {/* ── LEAPS Tab ── */}
        {subTab === 'leaps' && !loading && (
          <motion.div
            key="leaps"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="text-lg font-display font-bold text-white">LEAPS Scanner</h3>
                <p className="text-sm text-gray-500">Long-dated calls with high leverage and low theta decay</p>
              </div>
              <button
                onClick={loadLeaps}
                className="px-4 py-2 bg-[var(--accent-violet)]/20 hover:bg-[var(--accent-violet)]/30 text-[var(--accent-violet)] rounded-[var(--radius-md)] text-sm font-semibold transition-colors"
              >
                Scan LEAPS
              </button>
            </div>

            {leapsResults.length === 0 ? (
              <div className="text-center py-16 text-gray-500">
                <p className="text-lg mb-1 font-display">No LEAPS data yet</p>
                <p className="text-sm">Hit "Scan LEAPS" to find long-dated opportunities</p>
              </div>
            ) : (
              <div className="grid gap-3">
                {leapsResults.map((l) => (
                  <motion.div
                    key={`${l.ticker}-${l.strike}-${l.expiration}`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-4 bg-[var(--surface-800)]/70 border border-[var(--surface-600)]/40 rounded-[var(--radius-lg)]"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className="text-lg font-display font-bold text-white">{l.ticker}</span>
                        <span className="text-sm text-gray-300">{l.name}</span>
                        <span className={`px-2 py-0.5 rounded-[var(--radius-sm)] text-xs font-semibold ${
                          l.score >= 70 ? 'bg-emerald-600' : l.score >= 50 ? 'bg-amber-600' : 'bg-gray-600'
                        } text-white`}>
                          Score: {l.score}
                        </span>
                      </div>
                      <span className="font-mono text-sm text-gray-400">{l.days_to_expiry}d</span>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm mb-2">
                      <div>
                        <span className="text-gray-500">Price:</span>
                        <span className="ml-2 font-mono text-white">${l.current_price.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Strike:</span>
                        <span className="ml-2 font-mono text-[var(--accent-cyan)]">${l.strike}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Premium:</span>
                        <span className="ml-2 font-mono text-[var(--accent-amber)]">${l.premium.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Delta:</span>
                        <span className="ml-2 font-mono text-white">{l.delta.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Leverage:</span>
                        <span className="ml-2 font-mono text-[var(--accent-emerald)]">{l.leverage_ratio.toFixed(1)}x</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 text-sm">
                      <span className="text-gray-500">
                        IV: <span className="font-mono text-white">{l.iv.toFixed(1)}%</span>
                      </span>
                      <span className="text-gray-500">
                        IV Rank: <span className="font-mono text-[var(--accent-amber)]">{l.iv_rank}</span>
                      </span>
                      <span className="text-gray-500">
                        B/E: <span className="font-mono text-white">${l.breakeven.toFixed(2)}</span>
                        <span className="text-gray-600 ml-1">({l.breakeven_pct.toFixed(1)}%)</span>
                      </span>
                    </div>

                    {l.flags.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {l.flags.map((f, i) => (
                          <span
                            key={i}
                            className="px-2 py-0.5 bg-[var(--accent-cyan)]/15 rounded-[var(--radius-sm)] text-xs text-[var(--accent-cyan)]"
                          >
                            {f}
                          </span>
                        ))}
                      </div>
                    )}
                  </motion.div>
                ))}
              </div>
            )}
          </motion.div>
        )}

        {/* ── Strategy Finder Tab ── */}
        {subTab === 'strategies' && !loading && (
          <motion.div
            key="strategies"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            <h3 className="text-lg font-display font-bold text-white mb-1">Target-Price Strategy Finder</h3>
            <p className="text-sm text-gray-500 mb-5">
              Enter a ticker and your price target -- we'll find the best options strategy
            </p>

            <div className="flex items-end gap-3 mb-6">
              <div>
                <label className="block text-xs text-gray-500 mb-1 uppercase tracking-wider">Ticker</label>
                <input
                  type="text"
                  value={stratTicker}
                  onChange={(e) => setStratTicker(e.target.value.toUpperCase())}
                  placeholder="AAPL"
                  className="w-28 px-3 py-2 bg-[var(--surface-800)] border border-[var(--surface-600)] rounded-[var(--radius-md)] text-white font-mono text-sm uppercase tracking-wider focus:border-[var(--accent-violet)] focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 uppercase tracking-wider">Target Price</label>
                <input
                  type="number"
                  value={stratTarget}
                  onChange={(e) => setStratTarget(e.target.value)}
                  placeholder="250.00"
                  className="w-32 px-3 py-2 bg-[var(--surface-800)] border border-[var(--surface-600)] rounded-[var(--radius-md)] text-white font-mono text-sm focus:border-[var(--accent-violet)] focus:outline-none"
                />
              </div>
              <button
                onClick={loadStrategies}
                disabled={!stratTicker || !stratTarget}
                className={`px-5 py-2 rounded-[var(--radius-md)] text-sm font-semibold transition-colors ${
                  stratTicker && stratTarget
                    ? 'bg-[var(--accent-violet)]/20 hover:bg-[var(--accent-violet)]/30 text-[var(--accent-violet)]'
                    : 'bg-[var(--surface-700)] text-gray-500 cursor-not-allowed'
                }`}
              >
                Find Strategies
              </button>
            </div>

            {stratResults.length === 0 ? (
              <div className="text-center py-16 text-gray-500">
                <p className="text-lg mb-1 font-display">Enter a ticker and target to begin</p>
              </div>
            ) : (
              <div className="grid gap-3">
                {stratResults.map((s, idx) => (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    className="p-4 bg-[var(--surface-800)]/70 border border-[var(--surface-600)]/40 rounded-[var(--radius-lg)]"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className="text-lg font-display font-bold text-white">{s.ticker}</span>
                        <span className="px-2 py-0.5 bg-[var(--accent-violet)]/20 rounded-[var(--radius-sm)] text-xs text-[var(--accent-violet)] font-semibold">
                          {s.strategy}
                        </span>
                        <span className={`px-2 py-0.5 rounded-[var(--radius-sm)] text-xs font-semibold ${
                          s.score >= 70 ? 'bg-emerald-600' : s.score >= 50 ? 'bg-amber-600' : 'bg-gray-600'
                        } text-white`}>
                          Score: {s.score}
                        </span>
                      </div>
                      <span className="text-sm font-mono text-[var(--accent-emerald)]">
                        PoP: {(s.probability_of_profit * 100).toFixed(0)}%
                      </span>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                      <div>
                        <span className="text-gray-500">Current:</span>
                        <span className="ml-2 font-mono text-white">${s.current_price.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Target:</span>
                        <span className="ml-2 font-mono text-[var(--accent-emerald)]">${s.target_price.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Max Profit:</span>
                        <span className="ml-2 font-mono text-[var(--accent-emerald)]">${s.max_profit.toFixed(0)}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Max Loss:</span>
                        <span className="ml-2 font-mono text-[var(--accent-rose)]">${s.max_loss.toFixed(0)}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">R:R:</span>
                        <span className="ml-2 font-mono text-[var(--accent-cyan)]">{s.risk_reward.toFixed(1)}</span>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
