# MetaBet - Polymarket Trader Analytics

**Sophisticated trader detection system for Polymarket prediction markets**

MetaBet identifies traders with information advantages on Polymarket by analyzing betting patterns, timing strategies, and historical performance across resolved markets.

---

## 🎯 Project Goal

Detect traders who consistently demonstrate edge through:
- **Contrarian betting** that wins against majority positions
- **Late-entry timing** (betting close to market resolution)
- **High ROI** across multiple markets over time
- **Suspicious patterns** like hedging or duplicate bets

This is **NOT** insider trading detection (we lack the resources/authority). Instead, we surface traders with information asymmetry for public awareness and betting strategy insights.

---

## 🏗️ Architecture

### Data Collection Pipeline

**1. Polymarket API Scraper** (`test_api.py`)
- Fetches resolved markets from last 6 months
- Analyzes trade timing relative to resolution
- Identifies contrarian positions that won
- No API key required (public read-only endpoints)

**2. User Profile Scraper** (`backend/`)
- Selenium-based scraping of Polymarket user profiles
- Extracts betting history, win/loss records, P&L
- Detects duplicate bets and hedging patterns
- Proper deduplication using content hashing

### Analysis Outputs

- `polymarket_leaderboard_monthly.csv` - Top traders by volume
- `potential_whales.csv` - Flagged sophisticated traders
- `backend/polymarket_user_stats.csv` - Detailed user statistics

---

## 🚀 Quick Start

### Prerequisites

```bash
Python 3.8+
Chrome browser (for Selenium scraping)
```

### Installation

```bash
git clone https://github.com/VitalyChait/MetaBet.git
cd MetaBet
git checkout analytics

# Install dependencies
pip install -r requirements.txt

# Set up environment (optional)
cp .env_example .env
# Edit .env if needed
```

### Usage

#### 1. Analyze Polymarket API Data

```bash
# Fetch resolved markets and find sophisticated traders
python test_api.py
```

This will:
- Pull 6 months of resolved markets
- Identify users who bet contrarian + late + won
- Output suspicious trading patterns

#### 2. Scrape User Profiles

```bash
# Analyze specific users from leaderboard
python backend/scraper.py --user-limit 10 --bet-limit 100 \
  --csv-file polymarket_leaderboard_monthly.csv \
  --output-file backend/polymarket_user_stats.csv
```

**Options:**
- `--user-limit N` - Process first N users from CSV
- `--bet-limit N` - Scrape up to N bets per user
- `--csv-file PATH` - Input CSV with user profiles
- `--output-file PATH` - Where to save analysis

---

## 📊 Signal Detection

### What Makes a Trader "Sophisticated"?

**Primary Signals:**
1. **Late Entry** - First bet within 24h of resolution
2. **Contrarian Win** - Bet against majority and won
3. **Consistent Performance** - Pattern repeats across markets

**Secondary Signals:**
4. **High ROI** - Net positive P&L over time
5. **Strategic Hedging** - Betting both outcomes on same market
6. **Duplicate Patterns** - Multiple identical bets (potential wash trading)

### Example Output

```
Found 3 traders with edge (contrarian + late entry + win):
  
  1. User: 0xa3f2b1c4d5...
     Volume: $15,234.50
     Position: NO (contrarian)
     Last trade: 8.3h before resolution
     Trading window: 2.1h
     Number of trades: 7
```

---

## 🔍 Key Insights

### Timing Analysis

```
Resolution Time
     ↑
     |
     |  ← Early Exit (>7 days before) = Risk management
     |
     |  ← Active Trading Window
     |
     |  ← Late Entry (<24h before) = Potential edge
     |
Resolution
```

**Why timing matters:**
- **Early traders**: Public information only
- **Late traders**: May have better information flow OR got lucky
- **Pattern across markets**: Distinguishes skill from luck

### Behavioral Patterns

- **Hedging**: Betting both YES/NO on same market (risk mitigation or gaming bonuses)
- **Duplicates**: Multiple identical bets (could indicate bot activity or wash trading)
- **Win Rate**: Raw wins/losses vs. net P&L (some lose often but win big)

---

## 📁 Project Structure

```
MetaBet/
├── backend/
│   ├── scraper.py              # Selenium profile scraper (FIXED VERSION)
│   └── polymarket_user_stats.csv  # Analysis output
├── tests/
│   └── [test files]
├── test_api.py                 # Polymarket API analyzer
├── polymarket_leaderboard_monthly.csv  # Top traders
├── potential_whales.csv        # Flagged users
├── requirements.txt
├── .env_example
└── README.md
```

---

## ⚠️ Important Notes

### Limitations

1. **Not Proof of Insider Trading**
   - We identify patterns, not prove intent
   - Many explanations for "edge" (research, speed, modeling)
   
2. **False Positives**
   - Luck exists - single market wins don't mean anything
   - Need pattern across multiple markets to be meaningful

3. **Data Quality**
   - Polymarket API may have rate limits
   - Profile scraping depends on site structure (breaks if UI changes)
   - Historical data limited to available records

### Ethical Considerations

- This is for **public awareness**, not accusations
- Users flagged should be investigated further, not assumed guilty
- Prediction markets BENEFIT from informed traders (price discovery)
- We're identifying asymmetry, not necessarily wrongdoing

---

## 🛠️ Technical Details

### API Endpoints Used

```python
# Market data
https://gamma-api.polymarket.com/markets

# Trade data  
https://data-api.polymarket.com/trades

# User positions
https://data-api.polymarket.com/positions
```

### Scraping Strategy

- **Immediate parsing** - Extract data as we find it (no stale elements)
- **Content-based deduplication** - Hash of title+outcome+amount
- **Scroll detection** - Stop when no new bets found in 2 iterations
- **Rate limiting** - 2s delay between users

### Dependencies

- `requests` - API calls
- `pandas` - Data manipulation
- `selenium` - Profile scraping
- `webdriver-manager` - Chrome driver management

---

## 🤝 Contributing

This is a hackathon project, but contributions welcome!

Areas for improvement:
- Cross-reference with social media activity
- Build predictive model for "edge" detection
- Real-time monitoring dashboard
- Statistical significance testing

---

## 📝 License

MIT License - See [LICENSE](LICENSE) file

---

## 🎓 Research Context

Built as part of an AI Agent hackathon exploring:
- Information asymmetry in prediction markets
- Behavioral pattern detection
- Market microstructure analysis

**Not affiliated with Polymarket or any regulatory body.**

---

## 📧 Contact

For questions or collaboration:
- GitHub: [@VitalyChait](https://github.com/VitalyChait)
- Open an issue in this repo

---

## 🙏 Acknowledgments

- Polymarket for open data APIs
- Prediction market research community
- Fellow hackathon participants

**Remember:** Sophisticated traders are not necessarily malicious. They might just be really good at research, modeling, or information processing. This tool helps identify them - interpretation is up to you.