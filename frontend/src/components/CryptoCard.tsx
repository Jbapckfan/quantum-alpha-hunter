import { motion } from 'framer-motion';
import type { CryptoResult } from '../types';

interface CryptoCardProps {
  crypto: CryptoResult;
  onAnalyze: (ticker: string) => void;
}

const trendColor: Record<string, string> = {
  BULLISH: 'text-[var(--accent-emerald)]',
  RECOVERING: 'text-[var(--accent-amber)]',
  NEUTRAL: 'text-gray-400',
  BEARISH: 'text-[var(--accent-rose)]',
};

const trendBg: Record<string, string> = {
  BULLISH: 'bg-emerald-600',
  RECOVERING: 'bg-amber-600',
  NEUTRAL: 'bg-gray-600',
  BEARISH: 'bg-red-600',
};

function formatPrice(price: number): string {
  if (price < 0.01) return price.toFixed(6);
  if (price < 1) return price.toFixed(4);
  return price.toFixed(2);
}

function formatVolume(vol: number): string {
  if (vol >= 1e9) return `$${(vol / 1e9).toFixed(1)}B`;
  if (vol >= 1e6) return `$${(vol / 1e6).toFixed(1)}M`;
  if (vol >= 1e3) return `$${(vol / 1e3).toFixed(0)}K`;
  return `$${vol.toFixed(0)}`;
}

export default function CryptoCard({ crypto: c, onAnalyze }: CryptoCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="p-4 bg-[var(--surface-800)]/70 backdrop-blur-sm border border-[var(--surface-600)]/40 rounded-[var(--radius-lg)] hover:border-[var(--accent-amber)]/30 transition-colors"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center gap-3 mb-1 flex-wrap">
            <span className="text-xl font-display font-bold text-white tracking-tight">
              {c.ticker.replace('-USD', '')}
            </span>
            <span className="text-lg font-mono font-semibold text-[var(--accent-amber)]">
              ${formatPrice(c.price)}
            </span>
            <span
              className={`px-2 py-0.5 rounded-[var(--radius-sm)] text-xs font-semibold ${
                c.score >= 60 ? 'bg-emerald-600' : c.score >= 40 ? 'bg-amber-600' : c.score >= 25 ? 'bg-orange-600' : 'bg-gray-600'
              } text-white`}
            >
              {c.score}/{c.max_score}
            </span>
            <span className={`text-sm font-semibold ${trendColor[c.trend] ?? 'text-gray-400'}`}>
              {c.trend}
            </span>
          </div>

          <div className="text-sm text-gray-400 mb-2">{c.name}</div>

          {/* Price changes */}
          <div className="flex flex-wrap gap-4 mb-3 text-sm">
            {[
              { label: '24h', val: c.change_24h },
              { label: '7d', val: c.change_7d },
              { label: '30d', val: c.change_30d },
            ].map(({ label, val }) => (
              <div key={label}>
                <span className="text-gray-500">{label}:</span>
                <span
                  className={`ml-1 font-medium font-mono ${
                    val >= 0 ? 'text-[var(--accent-emerald)]' : 'text-[var(--accent-rose)]'
                  }`}
                >
                  {val >= 0 ? '+' : ''}
                  {val}%
                </span>
              </div>
            ))}
          </div>

          {/* Flags */}
          <div className="flex flex-wrap gap-1.5 mb-3">
            {c.flags.map((flag, i) => (
              <span
                key={i}
                className="px-2 py-0.5 bg-[var(--accent-amber)]/15 rounded-[var(--radius-sm)] text-xs text-[var(--accent-amber)]"
              >
                {flag}
              </span>
            ))}
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Volume:</span>
              <span className="ml-2 text-[var(--accent-cyan)]">{formatVolume(c.volume_24h)}</span>
              {c.volume_ratio >= 2 && (
                <span className="ml-1 text-[var(--accent-emerald)]">({c.volume_ratio}x)</span>
              )}
            </div>
            <div>
              <span className="text-gray-500">RSI:</span>
              <span
                className={`ml-2 font-mono ${
                  c.rsi > 70
                    ? 'text-[var(--accent-rose)]'
                    : c.rsi < 30
                      ? 'text-[var(--accent-emerald)]'
                      : 'text-[var(--accent-amber)]'
                }`}
              >
                {c.rsi}
              </span>
            </div>
            <div>
              <span className="text-gray-500">From ATH:</span>
              <span className="ml-2 text-[var(--accent-rose)]">-{c.drawdown_from_ath}%</span>
            </div>
            <div>
              <span className="text-gray-500">Rally:</span>
              <span className="ml-2 text-[var(--accent-emerald)]">+{c.rally_from_30d_low}%</span>
            </div>
          </div>

          {/* EMA info */}
          <div className="mt-3 pt-3 border-t border-[var(--surface-600)]/40 text-sm font-mono">
            <span className="text-gray-500">EMAs:</span>
            <span className="ml-2">
              20: <span className="text-[var(--accent-cyan)]">${formatPrice(c.ema20)}</span> |{' '}
              50: <span className="text-[var(--accent-amber)]">${formatPrice(c.ema50)}</span>
            </span>
            {c.price > c.ema20 && c.price > c.ema50 && (
              <span className="ml-2 text-[var(--accent-emerald)]">(Above Both)</span>
            )}
          </div>
        </div>

        {/* Action */}
        <div className="flex flex-col gap-2 ml-4 shrink-0">
          <button
            onClick={() => onAnalyze(c.ticker)}
            className="px-3 py-1.5 bg-[var(--accent-amber)]/20 hover:bg-[var(--accent-amber)]/30 text-[var(--accent-amber)] rounded-[var(--radius-md)] text-sm font-semibold transition-colors"
          >
            Chart
          </button>
        </div>
      </div>
    </motion.div>
  );
}
