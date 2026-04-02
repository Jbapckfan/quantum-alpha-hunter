import { motion } from 'framer-motion';
import type { WatchlistItem } from '../types';

interface WatchlistCardProps {
  item: WatchlistItem;
  onAnalyze: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function WatchlistCard({ item, onAnalyze, onRemove }: WatchlistCardProps) {
  const pnlColor = (item.pnl_pct ?? 0) >= 0 ? 'text-[var(--accent-emerald)]' : 'text-[var(--accent-rose)]';
  const statusColor =
    item.status === 'TARGET_HIT'
      ? 'bg-emerald-700'
      : item.status === 'STOPPED_OUT'
        ? 'bg-red-700'
        : 'bg-[var(--accent-cyan)]/30 text-[var(--accent-cyan)]';

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="p-4 bg-[var(--surface-800)]/70 backdrop-blur-sm border border-[var(--surface-600)]/40 rounded-[var(--radius-lg)] hover:border-[var(--surface-500)] transition-colors"
    >
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center gap-3 mb-1 flex-wrap">
            <span className="text-xl font-display font-bold text-white tracking-tight">
              {item.ticker}
            </span>
            <span className={`px-2 py-0.5 rounded-[var(--radius-sm)] text-xs font-semibold ${statusColor}`}>
              {item.status}
            </span>
            <span className="text-sm text-gray-400 font-mono">Score: {item.score}</span>
          </div>

          {/* Company + sector */}
          <div className="mb-2">
            <span className="text-sm text-gray-300">{item.company_name || item.ticker}</span>
            {item.sector && item.sector !== 'Unknown' && (
              <span className="ml-2 px-2 py-0.5 bg-[var(--accent-violet)]/20 rounded-[var(--radius-sm)] text-xs text-[var(--accent-violet)]">
                {item.sector}
              </span>
            )}
            {item.industry && item.industry !== 'Unknown' && (
              <span className="ml-1 text-xs text-gray-500">&middot; {item.industry}</span>
            )}
          </div>

          {/* Entry info */}
          <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-[var(--surface-700)]/60 rounded-[var(--radius-md)] text-sm mb-3">
            <span className="text-gray-400">Added {formatDate(item.added_at)} @</span>
            <span className="font-medium font-mono text-white">${item.entry_price}</span>
            {item.current_price && item.pnl_pct !== undefined && (
              <span className={`flex items-center gap-1 font-medium font-mono ${item.pnl_pct >= 0 ? 'text-[var(--accent-emerald)]' : 'text-[var(--accent-rose)]'}`}>
                {item.pnl_pct >= 0 ? (
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M14.707 10.293a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 12.586V5a1 1 0 012 0v7.586l2.293-2.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                )}
                {item.pnl_pct >= 0 ? '+' : ''}
                {item.pnl_pct}%
              </span>
            )}
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Current:</span>
              <span className="ml-2 text-white font-medium font-mono">${item.current_price ?? '...'}</span>
            </div>
            <div>
              <span className="text-gray-500">P&L:</span>
              <span className={`ml-2 font-medium font-mono ${pnlColor}`}>
                {item.pnl_pct !== undefined
                  ? `${item.pnl_pct >= 0 ? '+' : ''}${item.pnl_pct}%`
                  : '...'}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Stop:</span>
              <span className="ml-2 text-[var(--accent-rose)] font-mono">${item.stop_price}</span>
            </div>
            <div>
              <span className="text-gray-500">Target:</span>
              <span className="ml-2 text-[var(--accent-emerald)] font-mono">${item.target_price}</span>
            </div>
          </div>

          {/* Flags */}
          <div className="flex flex-wrap gap-1.5 mt-3">
            {item.flags.slice(0, 6).map((flag, i) => (
              <span
                key={i}
                className="px-2 py-0.5 bg-[var(--surface-700)] rounded-[var(--radius-sm)] text-xs text-gray-300"
              >
                {flag}
              </span>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-2 ml-4 shrink-0">
          <button
            onClick={() => onAnalyze(item.ticker)}
            className="px-3 py-1.5 bg-[var(--accent-cyan)]/20 hover:bg-[var(--accent-cyan)]/30 text-[var(--accent-cyan)] rounded-[var(--radius-md)] text-sm font-semibold transition-colors"
          >
            Chart
          </button>
          <button
            onClick={() => onRemove(item.ticker)}
            className="px-3 py-1.5 bg-[var(--accent-rose)]/20 hover:bg-[var(--accent-rose)]/30 text-[var(--accent-rose)] rounded-[var(--radius-md)] text-sm font-semibold transition-colors"
          >
            Remove
          </button>
        </div>
      </div>
    </motion.div>
  );
}
