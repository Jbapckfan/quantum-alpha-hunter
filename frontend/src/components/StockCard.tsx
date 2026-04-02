import { motion } from 'framer-motion';
import type { PatternResult } from '../types';

interface StockCardProps {
  result: PatternResult;
  onAnalyze: (ticker: string) => void;
  onAddToWatchlist: (ticker: string) => void;
  isHighConfidence?: boolean;
}

const stageColor: Record<string, string> = {
  EARLY: 'text-[var(--accent-emerald)]',
  MID: 'text-[var(--accent-amber)]',
  LATE: 'text-orange-400',
  EXTENDED: 'text-[var(--accent-rose)]',
};

function scoreBadge(score: number): string {
  if (score >= 80) return 'bg-emerald-600';
  if (score >= 65) return 'bg-amber-600';
  if (score >= 50) return 'bg-orange-600';
  return 'bg-red-600';
}

export default function StockCard({
  result: r,
  onAnalyze,
  onAddToWatchlist,
  isHighConfidence,
}: StockCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={`p-4 bg-[var(--surface-800)]/70 backdrop-blur-sm border ${
        isHighConfidence
          ? 'border-[var(--accent-emerald)]/40'
          : 'border-[var(--surface-600)]/40'
      } rounded-[var(--radius-lg)] hover:border-[var(--surface-500)] transition-colors`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          {/* Header row */}
          <div className="flex items-center gap-3 mb-1 flex-wrap">
            <span className="text-xl font-display font-bold text-white tracking-tight">
              {r.ticker}
            </span>
            <span className="text-lg font-mono font-semibold text-[var(--accent-emerald)]">
              ${r.price}
            </span>
            <span
              className={`px-2 py-0.5 rounded-[var(--radius-sm)] text-xs font-semibold ${scoreBadge(r.score)} text-white`}
            >
              {r.score}
            </span>
            <span
              className={`text-sm font-semibold ${stageColor[r.stage] ?? 'text-gray-400'}`}
            >
              {r.stage}
            </span>
            {r.confidence && (
              <span className="px-2 py-0.5 rounded-[var(--radius-sm)] text-xs font-semibold bg-emerald-700 text-white">
                {r.confidence}
              </span>
            )}
          </div>

          {/* Company info */}
          <div className="mb-2">
            <span className="text-sm text-gray-300">{r.name}</span>
            {r.sector && r.sector !== 'Unknown' && (
              <span className="ml-2 px-2 py-0.5 bg-[var(--accent-violet)]/20 rounded-[var(--radius-sm)] text-xs text-[var(--accent-violet)]">
                {r.sector}
              </span>
            )}
          </div>

          {r.description && (
            <p className="text-xs text-gray-500 mb-2 italic leading-relaxed">
              {r.description}
            </p>
          )}

          {/* Flags */}
          <div className="flex flex-wrap gap-1.5 mb-3">
            {r.flags.map((flag, i) => (
              <span
                key={i}
                className="px-2 py-0.5 bg-[var(--surface-700)] rounded-[var(--radius-sm)] text-xs text-gray-300"
              >
                {flag}
              </span>
            ))}
          </div>

          {/* Metrics grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Drawdown:</span>
              <span className="ml-2 text-[var(--accent-rose)]">{r.drawdown}%</span>
            </div>
            <div>
              <span className="text-gray-500">Rally:</span>
              <span className="ml-2 text-[var(--accent-emerald)]">+{r.rally_from_low}%</span>
            </div>
            <div>
              <span className="text-gray-500">Vol Exp:</span>
              <span className="ml-2 text-[var(--accent-cyan)]">{r.vol_expansion}x</span>
            </div>
            <div>
              <span className="text-gray-500">RSI:</span>
              <span className="ml-2 text-[var(--accent-amber)]">{r.rsi}</span>
            </div>
          </div>

          {/* Analyst coverage */}
          {(r.num_analysts > 0 || r.upside_to_target) && (
            <div className="mt-3 p-2 bg-[var(--surface-700)]/40 rounded-[var(--radius-md)] text-sm">
              <div className="flex flex-wrap items-center gap-4">
                {r.recommendation &&
                  r.recommendation !== 'N/A' && (
                    <span
                      className={`px-2 py-0.5 rounded-[var(--radius-sm)] text-xs font-semibold uppercase ${
                        r.recommendation === 'buy' || r.recommendation === 'strong_buy'
                          ? 'bg-emerald-700'
                          : r.recommendation === 'sell' || r.recommendation === 'strong_sell'
                            ? 'bg-red-700'
                            : 'bg-amber-700'
                      }`}
                    >
                      {r.recommendation.replace('_', ' ')}
                    </span>
                  )}
                {r.target_mean && (
                  <span>
                    <span className="text-gray-500">Target:</span>
                    <span className="ml-1 text-[var(--accent-emerald)]">
                      ${r.target_mean}
                    </span>
                    {r.upside_to_target && (
                      <span className="text-[var(--accent-emerald)]">
                        {' '}
                        (+{r.upside_to_target}%)
                      </span>
                    )}
                  </span>
                )}
                {r.target_high && (
                  <span>
                    <span className="text-gray-500">High:</span>
                    <span className="ml-1 text-[var(--accent-amber)]">${r.target_high}</span>
                  </span>
                )}
                {r.num_analysts > 0 && (
                  <span className="text-gray-500">
                    {r.num_analysts} analyst{r.num_analysts > 1 ? 's' : ''}
                  </span>
                )}
              </div>

              {/* Price target rows */}
              {r.upgrades && r.upgrades.length > 0 && r.upgrades[0].firm !== 'Unknown' && (
                <div className="mt-2 pt-2 border-t border-[var(--surface-600)]/50">
                  <span className="text-gray-500 text-xs">Analyst Price Targets: </span>
                  <div className="mt-1 space-y-1">
                    {r.upgrades.slice(0, 5).map((u, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between text-xs bg-[var(--surface-700)]/40 rounded-[var(--radius-sm)] px-2 py-1"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-gray-500 w-16">
                            {u.date?.slice(5) || ''}
                          </span>
                          <span className="text-gray-300 font-medium truncate max-w-[120px]">
                            {u.firm}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          {u.currentTarget && (
                            <span className="flex items-center gap-1">
                              {u.priorTarget && u.priorTarget !== u.currentTarget && (
                                <>
                                  <span className="text-gray-500">${u.priorTarget}</span>
                                  <span className="text-gray-600">&rarr;</span>
                                </>
                              )}
                              <span
                                className={`font-medium ${
                                  u.currentTarget > r.price
                                    ? 'text-[var(--accent-emerald)]'
                                    : 'text-[var(--accent-rose)]'
                                }`}
                              >
                                ${u.currentTarget}
                              </span>
                              {u.currentTarget > r.price && (
                                <span className="text-[var(--accent-emerald)]/60 text-[10px]">
                                  +
                                  {Math.round(
                                    ((u.currentTarget - r.price) / r.price) * 100,
                                  )}
                                  %
                                </span>
                              )}
                            </span>
                          )}
                          {u.toGrade && u.toGrade !== 'N/A' && (
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] ${
                                u.toGrade?.toLowerCase().includes('buy') ||
                                u.toGrade?.toLowerCase().includes('outperform')
                                  ? 'bg-emerald-500/20 text-emerald-400'
                                  : u.toGrade?.toLowerCase().includes('sell') ||
                                      u.toGrade?.toLowerCase().includes('underperform')
                                    ? 'bg-red-500/20 text-red-400'
                                    : 'bg-amber-500/20 text-amber-400'
                              }`}
                            >
                              {u.toGrade}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Trade plan */}
          <div className="mt-3 pt-3 border-t border-[var(--surface-600)]/40 text-sm font-mono">
            <span className="text-gray-500">Plan:</span>
            <span className="ml-2">
              Stop: <span className="text-[var(--accent-rose)]">${r.stop}</span> |{' '}
              T1: <span className="text-[var(--accent-emerald)]">${r.t1}</span> |{' '}
              T2: <span className="text-[var(--accent-emerald)]">${r.t2}</span> |{' '}
              +10R: <span className="text-[var(--accent-amber)]">${r.t4} (+{r.pct_to_10r}%)</span>
            </span>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-col gap-2 ml-4 shrink-0">
          <button
            onClick={() => onAnalyze(r.ticker)}
            className="px-3 py-1.5 bg-[var(--accent-cyan)]/20 hover:bg-[var(--accent-cyan)]/30 text-[var(--accent-cyan)] rounded-[var(--radius-md)] text-sm font-semibold transition-colors"
          >
            Chart
          </button>
          <button
            onClick={() => onAddToWatchlist(r.ticker)}
            className="px-3 py-1.5 bg-[var(--accent-emerald)]/20 hover:bg-[var(--accent-emerald)]/30 text-[var(--accent-emerald)] rounded-[var(--radius-md)] text-sm font-semibold transition-colors"
          >
            + Watch
          </button>
        </div>
      </div>
    </motion.div>
  );
}
