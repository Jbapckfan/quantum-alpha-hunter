// Quantum Alpha Hunter - Premium Dashboard JavaScript

// Sample data (in production, this will come from API)
const SAMPLE_DATA = {
    signals: [
        { ticker: 'OPEN', score: 92, change: '+12.4%', price: '$2.51', mcap: '$1.6B', type: 'STOCK', signals: ['COMPRESSION', 'INSIDER_BUY', 'OPTIONS_SWEEP'] },
        { ticker: 'RXRX', score: 88, change: '+8.7%', price: '$4.32', mcap: '$900M', type: 'STOCK', signals: ['COMPRESSION', 'VOLUME_SPIKE'] },
        { ticker: 'RGTI', score: 85, change: '+15.2%', price: '$1.89', mcap: '$450M', type: 'STOCK', signals: ['INSIDER_BUY', 'OPTIONS_CALL_FLOW'] },
        { ticker: 'SOL-USD', score: 82, change: '+5.3%', price: '$142.50', mcap: '$67B', type: 'CRYPTO', signals: ['COMPRESSION', 'VOLUME_SPIKE'] },
        { ticker: 'JMIA', score: 79, change: '+7.1%', price: '$3.45', mcap: '$380M', type: 'STOCK', signals: ['COMPRESSION', 'NEWS_CATALYST'] },
        { ticker: 'SRFM', score: 76, change: '+9.8%', price: '$1.12', mcap: '$250M', type: 'STOCK', signals: ['INSIDER_BUY', 'VOLUME_SPIKE'] },
        { ticker: 'MATIC-USD', score: 74, change: '+3.9%', price: '$0.58', mcap: '$5.4B', type: 'CRYPTO', signals: ['COMPRESSION'] },
        { ticker: 'PLTR', score: 71, change: '+4.2%', price: '$28.90', mcap: '$62B', type: 'STOCK', signals: ['OPTIONS_CALL_FLOW', 'NEWS_CATALYST'] },
    ],

    news: [
        { title: 'OPEN announces new expansion plans', ticker: 'OPEN', time: '5 min ago', sentiment: 'positive' },
        { title: 'RXRX AI drug discovery breakthrough', ticker: 'RXRX', time: '12 min ago', sentiment: 'positive' },
        { title: 'Quantum computing sector sees renewed interest', ticker: 'RGTI', time: '28 min ago', sentiment: 'positive' },
        { title: 'Solana network upgrade completed successfully', ticker: 'SOL-USD', time: '1 hour ago', sentiment: 'positive' },
        { title: 'African e-commerce market growth accelerates', ticker: 'JMIA', time: '2 hours ago', sentiment: 'positive' },
    ],

    insiderTrades: [
        { ticker: 'OPEN', insider: 'CEO John Smith', type: 'BUY', amount: '$250K', shares: '100,000', time: '2 hours ago' },
        { ticker: 'RGTI', insider: 'CFO Jane Doe', type: 'BUY', amount: '$180K', shares: '95,000', time: '4 hours ago' },
        { ticker: 'SRFM', insider: 'Director Bob Lee', type: 'BUY', amount: '$120K', shares: '107,000', time: '6 hours ago' },
        { ticker: 'RXRX', insider: 'CEO Alice Wong', type: 'BUY', amount: '$300K', shares: '69,000', time: '1 day ago' },
    ],

    optionsFlow: [
        { ticker: 'PLTR', type: 'CALL', strike: '$30', expiry: '2 weeks', premium: '$425K', sentiment: 'bullish' },
        { ticker: 'OPEN', type: 'CALL', strike: '$3.00', expiry: '1 month', premium: '$180K', sentiment: 'bullish' },
        { ticker: 'COIN', type: 'PUT', strike: '$200', expiry: '3 weeks', premium: '$290K', sentiment: 'bearish' },
        { ticker: 'RIOT', type: 'CALL', strike: '$15', expiry: '2 weeks', premium: '$150K', sentiment: 'bullish' },
    ],

    activity: [
        { type: 'NEW_SIGNAL', message: 'OPEN entered high conviction zone', time: 'Just now', icon: 'star', color: 'yellow' },
        { type: 'COMPRESSION', message: 'RXRX BB compression detected', time: '3 min ago', icon: 'compress', color: 'purple' },
        { type: 'INSIDER', message: 'RGTI CEO purchased $180K shares', time: '15 min ago', icon: 'user-secret', color: 'green' },
        { type: 'OPTIONS', message: 'PLTR unusual call flow detected', time: '22 min ago', icon: 'exchange-alt', color: 'blue' },
        { type: 'VOLUME', message: 'SOL-USD volume spike 3.2x average', time: '35 min ago', icon: 'chart-bar', color: 'orange' },
        { type: 'NEWS', message: 'JMIA featured in Financial Times', time: '1 hour ago', icon: 'newspaper', color: 'indigo' },
    ]
};

// Signal badge colors
const SIGNAL_COLORS = {
    'COMPRESSION': 'bg-purple-500/20 text-purple-400',
    'INSIDER_BUY': 'bg-green-500/20 text-green-400',
    'OPTIONS_SWEEP': 'bg-blue-500/20 text-blue-400',
    'OPTIONS_CALL_FLOW': 'bg-blue-500/20 text-blue-400',
    'VOLUME_SPIKE': 'bg-orange-500/20 text-orange-400',
    'NEWS_CATALYST': 'bg-indigo-500/20 text-indigo-400',
};

// Update last update time
function updateTime() {
    const now = new Date();
    document.getElementById('lastUpdate').textContent = now.toLocaleTimeString();
}

// Render top signals
function renderTopSignals() {
    const container = document.getElementById('topSignals');

    const html = SAMPLE_DATA.signals.map(signal => {
        const scoreColor = signal.score >= 80 ? 'text-green-400' : signal.score >= 70 ? 'text-yellow-400' : 'text-gray-400';
        const changeColor = signal.change.startsWith('+') ? 'text-green-400' : 'text-red-400';
        const typeColor = signal.type === 'STOCK' ? 'text-blue-400' : 'text-purple-400';

        const signalBadges = signal.signals.map(s => {
            const color = SIGNAL_COLORS[s] || 'bg-gray-500/20 text-gray-400';
            return `<span class="px-2 py-1 rounded text-xs ${color}">${s.replace('_', ' ')}</span>`;
        }).join(' ');

        return `
            <div class="bg-gray-700/50 rounded-lg p-4 hover:bg-gray-700 transition cursor-pointer">
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center space-x-3">
                        <div class="text-xl font-bold">${signal.ticker}</div>
                        <div class="text-sm ${typeColor}">${signal.type}</div>
                        <div class="text-2xl font-bold ${scoreColor}">${signal.score}</div>
                    </div>
                    <div class="text-right">
                        <div class="text-lg font-semibold">${signal.price}</div>
                        <div class="text-sm ${changeColor}">${signal.change}</div>
                    </div>
                </div>
                <div class="flex items-center justify-between">
                    <div class="text-sm text-gray-400">MCap: ${signal.mcap}</div>
                    <div class="flex items-center space-x-2">
                        ${signalBadges}
                    </div>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// Render news
function renderNews() {
    const container = document.getElementById('recentNews');

    const html = SAMPLE_DATA.news.map(news => {
        const sentimentIcon = news.sentiment === 'positive' ? 'arrow-up' : news.sentiment === 'negative' ? 'arrow-down' : 'minus';
        const sentimentColor = news.sentiment === 'positive' ? 'text-green-400' : news.sentiment === 'negative' ? 'text-red-400' : 'text-gray-400';

        return `
            <div class="border-l-2 border-purple-500 pl-3 hover:bg-gray-700/30 transition py-2 cursor-pointer">
                <div class="flex items-start justify-between">
                    <div class="flex-1">
                        <div class="font-medium text-sm mb-1">${news.title}</div>
                        <div class="text-xs text-gray-400">
                            <span class="text-blue-400">${news.ticker}</span> • ${news.time}
                        </div>
                    </div>
                    <i class="fas fa-${sentimentIcon} ${sentimentColor} text-xs mt-1"></i>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// Render insider trades
function renderInsiderTrades() {
    const container = document.getElementById('insiderTrades');

    const html = SAMPLE_DATA.insiderTrades.map(trade => {
        const typeColor = trade.type === 'BUY' ? 'text-green-400' : 'text-red-400';

        return `
            <div class="bg-gray-700/50 rounded-lg p-3 hover:bg-gray-700 transition">
                <div class="flex items-center justify-between mb-2">
                    <div class="font-bold text-blue-400">${trade.ticker}</div>
                    <div class="text-sm ${typeColor} font-semibold">${trade.type}</div>
                </div>
                <div class="text-sm text-gray-300 mb-1">${trade.insider}</div>
                <div class="flex items-center justify-between text-xs text-gray-400">
                    <span>${trade.amount} (${trade.shares} shares)</span>
                    <span>${trade.time}</span>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// Render options flow
function renderOptionsFlow() {
    const container = document.getElementById('optionsFlow');

    const html = SAMPLE_DATA.optionsFlow.map(option => {
        const typeColor = option.type === 'CALL' ? 'text-green-400' : 'text-red-400';
        const sentimentColor = option.sentiment === 'bullish' ? 'text-green-400' : 'text-red-400';

        return `
            <div class="bg-gray-700/50 rounded-lg p-3 hover:bg-gray-700 transition">
                <div class="flex items-center justify-between mb-2">
                    <div class="font-bold text-blue-400">${option.ticker}</div>
                    <div class="text-sm ${typeColor} font-semibold">${option.type}</div>
                </div>
                <div class="flex items-center justify-between text-sm mb-1">
                    <span class="text-gray-300">Strike: ${option.strike}</span>
                    <span class="text-gray-400">${option.expiry}</span>
                </div>
                <div class="flex items-center justify-between text-xs">
                    <span class="text-gray-400">Premium: ${option.premium}</span>
                    <span class="${sentimentColor} font-semibold">${option.sentiment.toUpperCase()}</span>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// Render activity feed
function renderActivity() {
    const container = document.getElementById('activityFeed');

    const html = SAMPLE_DATA.activity.map(activity => {
        return `
            <div class="flex items-start space-x-3">
                <div class="w-8 h-8 bg-${activity.color}-500/20 rounded-lg flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-${activity.icon} text-${activity.color}-400 text-xs"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <div class="text-sm text-gray-300">${activity.message}</div>
                    <div class="text-xs text-gray-500">${activity.time}</div>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// Create performance chart
function createPerformanceChart() {
    const ctx = document.getElementById('performanceChart').getContext('2d');

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            datasets: [
                {
                    label: 'Signal Performance',
                    data: [65, 72, 68, 79, 85, 82, 88],
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    tension: 0.4,
                    fill: true
                },
                {
                    label: 'Market Avg',
                    data: [50, 52, 48, 55, 53, 51, 54],
                    borderColor: '#718096',
                    backgroundColor: 'rgba(113, 128, 150, 0.05)',
                    tension: 0.4,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: '#9ca3af'
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#374151'
                    },
                    ticks: {
                        color: '#9ca3af'
                    }
                },
                x: {
                    grid: {
                        color: '#374151'
                    },
                    ticks: {
                        color: '#9ca3af'
                    }
                }
            }
        }
    });
}

// Create sentiment chart
function createSentimentChart() {
    const ctx = document.getElementById('sentimentChart').getContext('2d');

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Bullish', 'Neutral', 'Bearish'],
            datasets: [{
                data: [62, 23, 15],
                backgroundColor: [
                    'rgba(16, 185, 129, 0.8)',
                    'rgba(156, 163, 175, 0.8)',
                    'rgba(239, 68, 68, 0.8)'
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
}

// Initialize dashboard
function init() {
    updateTime();
    renderTopSignals();
    renderNews();
    renderInsiderTrades();
    renderOptionsFlow();
    renderActivity();
    createPerformanceChart();
    createSentimentChart();

    // Update time every second
    setInterval(updateTime, 1000);

    // Simulate real-time updates every 30 seconds
    setInterval(() => {
        // Add animation or update data here
        console.log('Dashboard refreshed');
    }, 30000);
}

// Start dashboard when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
