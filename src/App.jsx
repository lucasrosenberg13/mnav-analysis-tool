import React, { useState, useEffect } from 'react';
import { Mail, TrendingUp, DollarSign, Coins, Building2, Calculator, RefreshCw, ArrowLeft } from 'lucide-react';

// Configuration for different tickers
const TICKER_CONFIG = {
  SBET: {
    name: 'Sharplink Gaming',
    crypto: 'ETH',
    cryptoName: 'Ethereum',
    description: 'Gaming & Entertainment',
    gradient: 'from-green-500 to-blue-600'
  },
  // Add more tickers here as you expand
  // MSTR: {
  //   name: 'MicroStrategy',
  //   crypto: 'BTC',
  //   cryptoName: 'Bitcoin',
  //   description: 'Business Intelligence',
  //   gradient: 'from-orange-500 to-yellow-600'
  // }
};

// Update this with your Railway URL
const API_BASE = 'https://web-production-f9705.up.railway.app/api'

// Loading Spinner Component
const LoadingSpinner = () => (
  <div className="border-3 border-blue-200 border-t-blue-600 rounded-full w-6 h-6 animate-spin"></div>
);

// Ticker Selection Card Component
const TickerCard = ({ ticker, config, onSelect }) => (
  <button
    onClick={() => onSelect(ticker)}
    className={`bg-gradient-to-r ${config.gradient} hover:scale-105 text-white font-medium py-6 px-8 rounded-xl shadow-lg transition-all duration-200 flex items-center justify-center gap-4 w-full`}
  >
    <Coins className="h-6 w-6 text-white opacity-80" />
    <div className="text-left">
      <div className="text-lg font-bold">{ticker}</div>
      <div className="text-sm opacity-90">{config.name}</div>
      <div className="text-xs opacity-75">{config.crypto} Holdings</div>
    </div>
  </button>
);

// Loading Steps Component
const LoadingSteps = ({ currentStep }) => {
  const steps = [
    'Checking current data',
    'Looking up latest SEC filings',
    'Processing new information',
    'Calculating MNAV metrics'
  ];

  return (
    <div className="text-sm text-gray-300 space-y-1">
      {steps.map((step, index) => {
        const stepNumber = index + 1;
        const isCompleted = stepNumber < currentStep;
        const isCurrent = stepNumber === currentStep;
        
        return (
          <div
            key={stepNumber}
            className={`flex items-center gap-2 ${
              isCompleted ? 'text-green-400' : 
              isCurrent ? 'text-blue-400' : 
              'opacity-50'
            }`}
          >
            {isCompleted ? '✓' : isCurrent ? '⏳' : '⏳'}
            {step}
          </div>
        );
      })}
    </div>
  );
};

// Market Data Header Component
const MarketDataHeader = ({ data, config }) => (
  <div className="bg-blue-600 text-white p-6">
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="text-center">
        <div className="text-sm opacity-90">{config.cryptoName} Price</div>
        <div className="text-2xl font-bold">${data.eth_price.toLocaleString('en-US', {minimumFractionDigits: 2})}</div>
      </div>
      <div className="text-center">
        <div className="text-sm opacity-90">{data.ticker} Stock Price</div>
        <div className="text-2xl font-bold">${data.stock_price.toLocaleString('en-US', {minimumFractionDigits: 2})}</div>
      </div>
    </div>
  </div>
);

// Metric Card Component
const MetricCard = ({ icon: Icon, label, value, className = "" }) => (
  <div className={`bg-gray-800 rounded-lg p-4 text-center shadow-md ${className}`}>
    <div className="flex items-center justify-center gap-2 mb-2">
      <Icon className="h-4 w-4 text-gray-400" />
      <div className="text-sm text-gray-400">{label}</div>
    </div>
    <div className="text-xl font-bold text-white">{value}</div>
  </div>
);

// MNAV Metrics Section Component
const MNAVMetrics = ({ data, config }) => (
  <div className="p-8 bg-gray-900">
    <h2 className="text-2xl font-semibold text-white mb-6 flex items-center gap-2">
      <Calculator className="h-7 w-7 text-gray-400" />
      MNAV Metrics
    </h2>
    
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      <MetricCard
        icon={Coins}
        label={`${config.crypto} Holdings`}
        value={`${data.eth_holdings.toLocaleString()} ${config.crypto}`}
      />
      <MetricCard
        icon={Building2}
        label="Diluted Shares"
        value={data.diluted_shares.toLocaleString()}
      />
      <MetricCard
        icon={DollarSign}
        label="Treasury Value"
        value={`$${data.treasury_value.toLocaleString('en-US', {maximumFractionDigits: 0})}`}
      />
      <MetricCard
        icon={TrendingUp}
        label="MNAV per Share"
        value={`$${data.mnav_per_share.toLocaleString('en-US', {minimumFractionDigits: 2})}`}
      />
    </div>

    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
      <MetricCard
        icon={Building2}
        label="Market Cap"
        value={`$${data.market_cap.toLocaleString('en-US', {maximumFractionDigits: 0})}`}
        className="p-6"
      />
      <div className="bg-gray-800 rounded-lg p-6 text-center">
        <div className="flex items-center justify-center gap-2 mb-2">
          <Calculator className="h-4 w-4 text-gray-400" />
          <div className="text-sm text-gray-400">MNAV Multiple</div>
        </div>
        <div className="text-2xl font-bold text-white">{data.mnav_multiple.toFixed(2)}x</div>
        <div className="text-xs text-gray-500 mt-1">Market Cap / Treasury Value</div>
      </div>
    </div>

    <div className="bg-gray-800 rounded-lg p-4 text-sm text-white">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>Last Updated: <span className="font-medium">{data.last_updated}</span></div>
        <div>Filings Processed: <span className="font-medium">{data.filings_processed}</span></div>
      </div>
    </div>
  </div>
);

// Email Form Component
const EmailForm = ({ onSend, onCancel, isLoading }) => {
  const [email, setEmail] = useState('');

  const handleSubmit = () => {
    if (email.trim()) {
      onSend(email.trim());
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSubmit();
    }
  };

  return (
    <div className="p-8 bg-gray-900">
      <h2 className="text-2xl font-semibold text-white mb-6">Send Email Report</h2>
      
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Email Address
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyPress={handleKeyPress}
            className="w-full px-4 py-3 border border-gray-600 rounded-lg bg-gray-800 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Enter your email address"
          />
        </div>
        
        <div className="flex gap-4">
          <button
            onClick={handleSubmit}
            disabled={isLoading || !email.trim()}
            className="flex-1 bg-blue-500 hover:bg-blue-600 disabled:bg-blue-400 text-white font-medium py-3 px-6 rounded-lg transition-colors duration-200 flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <LoadingSpinner />
                Sending...
              </>
            ) : (
              <>
                <Mail className="h-4 w-4" />
                Send Report
              </>
            )}
          </button>
          
          <button
            onClick={onCancel}
            className="px-6 py-3 border border-gray-600 rounded-lg text-gray-300 hover:bg-gray-800 transition-colors duration-200"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

// Error Display Component
const ErrorDisplay = ({ error, onRetry }) => (
  <div className="p-8 bg-gray-900">
    <div className="bg-red-900/50 border border-red-700 rounded-lg p-6">
      <h2 className="text-xl font-semibold text-red-400 mb-2">Error</h2>
      <p className="text-red-300 mb-4">{error}</p>
      <button
        onClick={onRetry}
        className="bg-red-600 hover:bg-red-700 text-white font-medium py-2 px-4 rounded-lg transition-colors duration-200"
      >
        Try Again
      </button>
    </div>
  </div>
);

// Main App Component
const MNAVApp = () => {
  const [currentView, setCurrentView] = useState('ticker-selection');
  const [selectedTicker, setSelectedTicker] = useState('');
  const [loadingStep, setLoadingStep] = useState(1);
  const [mnavData, setMnavData] = useState(null);
  const [error, setError] = useState('');
  const [emailLoading, setEmailLoading] = useState(false);

  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  const selectTicker = (ticker) => {
    setSelectedTicker(ticker);
    setCurrentView('loading');
    analyzeStock(ticker);
  };

  const analyzeStock = async (ticker) => {
    try {
      setError('');
      setLoadingStep(1);
      await sleep(500);
      
      setLoadingStep(2);
      await sleep(1000);
      
      setLoadingStep(3);
      await sleep(800);
      
      setLoadingStep(4);
      
      const response = await fetch(`${API_BASE}/analyze/${ticker}`);
      if (!response.ok) {
        throw new Error(`Analysis failed: ${response.statusText}`);
      }
      
      const data = await response.json();
      setMnavData(data);
      setCurrentView('results');
      
    } catch (err) {
      console.error('Analysis error:', err);
      setError(err.message);
      setCurrentView('error');
    }
  };

  const sendEmail = async (email) => {
    setEmailLoading(true);
    try {
      const response = await fetch(`${API_BASE}/email`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: email,
          mnav_data: mnavData
        })
      });

      if (!response.ok) {
        throw new Error(`Email sending failed: ${response.statusText}`);
      }

      alert('Email sent successfully!');
      setCurrentView('results');
      
    } catch (err) {
      console.error('Email error:', err);
      alert(`Failed to send email: ${err.message}`);
    } finally {
      setEmailLoading(false);
    }
  };

  const resetApp = () => {
    setCurrentView('ticker-selection');
    setSelectedTicker('');
    setMnavData(null);
    setError('');
    setLoadingStep(1);
  };

  const config = TICKER_CONFIG[selectedTicker] || {};

  return (
    <div className="bg-gray-950 min-h-screen font-sans">
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">MNAV Analysis Tool</h1>
          <p className="text-gray-400">Real-time Modified Net Asset Value analysis for crypto treasury companies</p>
        </div>

        {/* Main Card */}
        <div className="bg-gray-800 rounded-2xl shadow-xl overflow-hidden">
          {/* Ticker Selection */}
          {currentView === 'ticker-selection' && (
            <div className="p-8">
              <h2 className="text-2xl font-semibold text-white mb-6 text-center">Select Ticker</h2>
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-4 max-w-md mx-auto">
                  {Object.entries(TICKER_CONFIG).map(([ticker, config]) => (
                    <TickerCard
                      key={ticker}
                      ticker={ticker}
                      config={config}
                      onSelect={selectTicker}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Loading State */}
          {currentView === 'loading' && (
            <div className="p-8 text-center">
              <div className="flex flex-col items-center space-y-4">
                <LoadingSpinner />
                <h2 className="text-xl font-semibold text-gray-300">
                  Analyzing {selectedTicker}...
                </h2>
                <LoadingSteps currentStep={loadingStep} />
              </div>
            </div>
          )}

          {/* Results */}
          {currentView === 'results' && mnavData && (
            <>
              <MarketDataHeader data={mnavData} config={config} />
              <MNAVMetrics data={mnavData} config={config} />
              
              {/* Action Buttons */}
              <div className="p-8 bg-gray-900">
                <div className="flex flex-col sm:flex-row gap-4">
                  <button
                    onClick={() => setCurrentView('email')}
                    className="flex-1 bg-green-600 hover:bg-green-700 text-white font-medium py-3 px-6 rounded-lg transition-colors duration-200 flex items-center justify-center gap-2"
                  >
                    <Mail className="h-4 w-4" />
                    Email Report
                  </button>
                  
                  <button
                    onClick={resetApp}
                    className="flex-1 bg-gray-600 hover:bg-gray-700 text-white font-medium py-3 px-6 rounded-lg transition-colors duration-200 flex items-center justify-center gap-2"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    Analyze Another
                  </button>
                </div>
              </div>
            </>
          )}

          {/* Email Form */}
          {currentView === 'email' && (
            <EmailForm
              onSend={sendEmail}
              onCancel={() => setCurrentView('results')}
              isLoading={emailLoading}
            />
          )}

          {/* Error State */}
          {currentView === 'error' && (
            <ErrorDisplay error={error} onRetry={resetApp} />
          )}
        </div>

        {/* Footer */}
        <div className="text-center mt-8 text-gray-500 text-sm">
          <p>Powered by SEC EDGAR data and live market prices</p>
        </div>
      </div>
    </div>
  );
};

export default MNAVApp;