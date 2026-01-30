# Chess.com Game Analysis Toolkit

A collection of Python scripts for downloading, analysing, and evaluating Chess.com games using Stockfish.

## Overview

This toolkit provides:
- **PGN Download**: Fetch all your Chess.com games as individual PGN files
- **Parallel Analysis**: Analyse games with Stockfish using multiple CPU cores
- **Accuracy Metrics**: Calculate move accuracy using Lichess's open-source formula
- **Opening Classification**: Track openings using ECO codes with readable names
- **Performance Tracking**: Detailed statistics on blunders, mistakes, and book moves

## Features

- Downloads games incrementally (skips already-downloaded files)
- Parallel processing for fast analysis
- Opening book support (Polyglot format)
- Separate statistics for White and Black
- Lichess-compatible accuracy calculations
- Handles mate positions with distance-aware penalties
- Cross-platform (Windows, macOS, Linux)

## Requirements

### Python Packages
```bash
pip install requests python-chess
```

### External Dependencies
- **Stockfish**: Chess engine for analysis
  - Download from: https://stockfishchess.org/download/
  - Extract and note the path to the executable

### Optional
- **Polyglot Opening Book**: For identifying theoretical moves
  - Recommended: `theory_komodo.bin` or `gm2001.bin`
  - Available from: https://github.com/gmcheems-org/free-opening-books

## Installation

1. Clone this repository
2. Install Python dependencies:
   ```bash
   pip install requests python-chess
   ```
3. Download and install Stockfish
4. (Optional) Download an opening book

## Usage

### 1. Download Games from Chess.com

```bash
python chesscom_pgn_export.py <username> <email> [output_directory]
```

**Arguments:**
- `username`: Your Chess.com username
- `email`: Your email (for Chess.com API compliance)
- `output_directory`: (Optional) Directory to save PGN files (default: `pgn_files`)

**Example:**
```bash
python chesscom_pgn_export.py example_username user@example.com ~/chess/pgn_files
```

**Features:**
- Downloads all games from Chess.com API
- Skips already-downloaded files
- Filenames: `YYYY-MM-DD_HHMM_White_vs_Black.pgn`
- Includes 0.5s delay between requests (API-friendly)

### 2. Analyse Games with Stockfish

```bash
python analyse_pgn_files.py <pgn_directory> <stockfish_path> [options]
```

**Required Arguments:**
- `pgn_directory`: Directory containing PGN files
- `stockfish_path`: Path to Stockfish executable

**Optional Arguments:**
- `-o, --output`: Output file path (default: `analysis_results.tsv`)
- `-d, --depth`: Analysis depth (default: 18, higher = more accurate but slower)
- `-p, --processes`: Number of parallel processes (default: CPU core count - 4)
- `-b, --book`: Path to Polyglot opening book (.bin file)

**Example:**
```bash
python analyse_pgn_files.py ~/chess/pgn_files /usr/local/bin/stockfish \
    -o results.tsv \
    -d 20 \
    -p 4 \
    -b ~/chess/theory_komodo.bin
```

**Features:**
- Parallel processing across multiple CPU cores
- Skips already-analysed files (resume-friendly, increment your PGN directory and analysis at your leisure)
- Opening book support to account for theoretical moves
- Real-time progress updates

## Output Format

The analysis script generates a tab-separated values (TSV) file with these columns:

| Column | Description |
|--------|-------------|
| `filename` | PGN filename |
| `white_player` | White player's username |
| `black_player` | Black player's username |
| `white_elo` | White player's rating |
| `black_elo` | Black player's rating |
| `time_control` | Game type (bullet/blitz/rapid/classical/daily) |
| `opening` | ECO code (e.g., "B90") |
| `result` | Game result (1 = White won, -1 = Black won, 0 = Draw) |
| `white_accuracy` | White's accuracy percentage (0-100) |
| `white_best_moves` | Count of best moves (≤10cp loss) |
| `white_good_moves` | Count of good moves (11-25cp loss) |
| `white_inaccuracies` | Count of inaccuracies (26-50cp loss) |
| `white_mistakes` | Count of mistakes (51-100cp loss) |
| `white_blunders` | Count of blunders (>100cp loss) |
| `white_book_moves` | Count of theoretical opening moves |
| `white_total_moves` | Total moves by White |
| `black_*` | Same statistics for Black |

## Accuracy Calculation

Move accuracy uses the **Lichess open-source formula**:

1. **Convert centipawns to win percentage:**
   ```
   Win% = 50 + 50 * (2 / (1 + exp(-0.00368208 * centipawns)) - 1)
   ```

2. **Calculate move accuracy:**
   ```
   Accuracy% = 103.1668 * exp(-0.04354 * (winPercentBefore - winPercentAfter)) - 3.1669
   ```

**Mate handling:**
- Mate positions converted to centipawns: 10000 - (50 × moves_to_mate)
- Mate-in-1 = 10000cp, Mate-in-3 = 9900cp, etc.
- Missing mate entirely = large accuracy penalty
- Taking slightly longer mate = small penalty

**Source:** https://lichess.org/page/accuracy

## Move Classification

| Classification | Centipawn Loss |
|----------------|----------------|
| Best move | 0-10 |
| Good move | 11-25 |
| Inaccuracy | 26-50 |
| Mistake | 51-100 |
| Blunder | >100 |

## Time Control Classification

Based on Chess.com's time controls:

| Type | Base Time |
|------|-----------|
| Daily | t ≥ 1 day |
| Bullet | t < 3 mins |
| Blitz | 3 ≤ t ≤ 5 mins |
| Rapid | 5 < t ≤ 60 mins |
| Classical | t > 60 mins |

## Opening Names

The `eco_names.json` file provides ECO code → opening name mappings:

```python
import json

with open('eco_names.json') as f:
    opening_names = json.load(f)

# Map ECO codes to readable names
df['opening_name'] = df['opening'].map(opening_names)
```

The opening names have been manually shortened to a depth of 2 for example,
D16: Queen's Gambit Declined Slav, Smyslov variation → D16: QGD, Slav (depth of 2).


## Analysis Tips

### Performance
- Use `-p` to control CPU usage (default = n_cores - 4)
- Higher depth = more accurate but much slower (depth 20 vs 18 ≈ 2× slower)
- Opening books significantly speed up analysis by skipping theoretical moves

### Best Practices
- Run download script regularly to fetch new games
- Start with lower depth (16-18) for initial analysis
- Re-analyse important games at higher depth (22-25) if needed
- Use an opening book to improve accuracy and speed

### Resuming Analysis
Both scripts automatically skip already-processed files, so you can:
- Stop analysis at any time (Ctrl+C)
- Resume later without losing progress
- Re-run to analyse only new games

## Data Analysis Examples

### Using Pandas

```python
import pandas as pd

# Load results
df = pd.read_csv('analysis_results.tsv', sep='\t')

# Add datetime column
df['game_time'] = pd.to_datetime(
    df['filename'].str.extract(r'(\d{4}-\d{2}-\d{2}_\d{4})')[0],
    format='%Y-%m-%d_%H%M'
)

# Sort by date
df = df.sort_values('game_time').reset_index(drop=True)

# Split into your games as White and Black
white_games = df[df['white_player'] == 'your_username']
black_games = df[df['black_player'] == 'your_username']

# Calculate statistics by opening
opening_stats = df.groupby('opening_name').agg({
    'result': ['count', lambda x: (x == 1).sum()],
}).reset_index()
```

## Files

- `chesscom_pgn_export.py` - Downloads games from Chess.com API
- `analyse_pgn_files.py` - Analyses PGN files with Stockfish
- `eco_names.json` - ECO code to opening name mappings
- `eco_interpolated.json` - Detailed opening database (optional)

## Notes

### Accuracy Differences
The calculated accuracy may differ from Chess.com's and Lichess due to:
- Different engine versions
- Different analysis depths
- Different handling of book moves or endgames
- Proprietary adjustments

### API Rate Limits
The Chess.com API has rate limits:
- Serial requests (waiting between calls) are unlimited
- Parallel requests may return `429 Too Many Requests`
- The download script includes appropriate delays

### Opening Book Coverage
Opening books don't cover all openings:
- Rare openings (e.g., 1.c3) may not be in the book
- These will be analysed by the engine instead
- This is normal and expected behaviour

## Contributing

Contributions welcome! Please open an issue or pull request.

## License

MIT License - feel free to use and modify as needed, citing this original work.

## Acknowledgments

- **Lichess** for open-sourcing their accuracy formula
- **Chess.com** for their public API
- **Stockfish** team for the chess engine
- **python-chess** library maintainers
- **gmcheems-org (github)** providing a collection of free opening books 

## Support

For issues or questions:
1. Check the examples above
2. Verify Stockfish path is correct
3. Ensure PGN files are valid Chess.com format
4. Check that opening book (if used) is in Polyglot .bin format
