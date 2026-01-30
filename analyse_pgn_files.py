"""
Analyse Chess.com PGN files using Stockfish in parallel.
Outputs results to a TSV file.
Accuracy uses the Lichess open source calculations available at: https://lichess.org/page/accuracy
Standard openings are taken from the Chess.com PGN files under the ECO header.
"""

import chess
import chess.engine
import chess.pgn
import chess.polyglot
from pathlib import Path
from typing import Dict, List, Tuple
import multiprocessing as mp
from dataclasses import dataclass
import sys
import math

@dataclass
class MoveAnalysis:
    """Container for a single move's analysis."""
    eval_before: int  # centipawns
    eval_after: int   # centipawns
    best_move: chess.Move
    played_move: chess.Move
    
    
@dataclass
class GameStats:
    """Statistics for a single game."""
    filename: str
    white_player: str
    black_player: str
    white_elo: int
    black_elo: int
    time_control: str
    opening: str
    result: int  # 1 = White won, -1 = Black won, 0 = Draw
    white_accuracy: float
    white_best_moves: int
    white_good_moves: int
    white_inaccuracies: int
    white_mistakes: int
    white_blunders: int
    white_book_moves: int
    white_total_moves: int
    black_accuracy: float
    black_best_moves: int
    black_good_moves: int
    black_inaccuracies: int
    black_mistakes: int
    black_blunders: int
    black_book_moves: int
    black_total_moves: int
    

def classify_move(eval_loss: int) -> str:
    """
    Classify a move based on centipawn loss.
    
    Args:
        eval_loss: Centipawn loss (always positive)
        
    Returns:
        Classification: 'best', 'good', 'inaccuracy', 'mistake', or 'blunder'
    """
    if eval_loss <= 10:
        return 'best'
    elif eval_loss <= 25:
        return 'good'
    elif eval_loss <= 50:
        return 'inaccuracy'
    elif eval_loss <= 100:
        return 'mistake'
    else:
        return 'blunder'


def centipawns_to_win_percent(centipawns: int) -> float:
    """
    Convert centipawn evaluation to win percentage using Lichess formula.
    
    Args:
        centipawns: Engine evaluation in centipawns
        
    Returns:
        Win percentage (0-100)
    """
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * centipawns)) - 1)


def calculate_move_accuracy(win_percent_before: float, win_percent_after: float) -> float:
    """
    Calculate move accuracy using Lichess formula.
    
    Args:
        win_percent_before: Win percentage before the move
        win_percent_after: Win percentage after the move
        
    Returns:
        Move accuracy as a percentage (0-100)
    """
    win_percent_loss = win_percent_before - win_percent_after
    accuracy = 103.1668 * math.exp(-0.04354 * win_percent_loss) - 3.1669
    return max(0, min(100, accuracy))  # Clamp between 0 and 100


def calculate_accuracy(eval_pairs: List[Tuple[int, int]]) -> float:
    """
    Calculate average accuracy percentage from evaluation pairs.
    Uses Lichess's accuracy formula.
    
    Args:
        eval_pairs: List of (eval_before, eval_after) tuples in centipawns
        
    Returns:
        Accuracy as a percentage (0-100)
    """
    if not eval_pairs:
        return 0.0
    
    move_accuracies = []
    for eval_before, eval_after in eval_pairs:
        # Convert centipawn evaluations to win percentages
        win_before = centipawns_to_win_percent(eval_before)
        win_after = centipawns_to_win_percent(eval_after)
        
        # Calculate move accuracy
        accuracy = calculate_move_accuracy(win_before, win_after)
        move_accuracies.append(accuracy)
    
    return sum(move_accuracies) / len(move_accuracies)


def convert_mate_to_centipawns(score, mate_distance):
    """
    Convert mate scores to centipawns with distance-aware penalties.
    
    Args:
        score: The chess.engine.Score object
        mate_distance: Number of moves to mate (positive = White winning, negative = Black winning)
        
    Returns:
        Centipawn value
    """
    if mate_distance is None:
        # Not a mate position, return normal centipawn score
        return score.score()
    
    # Base mate value (very high but not infinite)
    base_mate_value = 10000
    
    # Penalty for longer mates: 100cp per move
    # Mate in 1 = 10000, mate in 2 = 9950, mate in 3 = 9900, etc.
    distance_penalty = abs(mate_distance) * 50
    
    # Calculate final value
    mate_value = base_mate_value - distance_penalty
    
    # Return with correct sign
    return mate_value if mate_distance > 0 else -mate_value


def get_eval_centipawns(info):
    """
    Extract centipawn evaluation, properly handling mate scores.
    """
    score = info['score'].white()
    
    # Check if it's a mate score
    mate = score.mate()
    
    if mate is not None:
        return convert_mate_to_centipawns(score, mate)
    else:
        return score.score()

        
def load_processed_files(output_file: str) -> set:
    """
    Load the set of already-processed filenames from the output file.
    
    Args:
        output_file: Path to the TSV output file
        
    Returns:
        Set of filenames that have already been processed
    """
    processed = set()
    output_path = Path(output_file)
    
    if output_path.exists():
        try:
            with open(output_file, 'r') as f:
                # Skip header
                next(f)
                for line in f:
                    # Extract filename (first column)
                    filename = line.split('\t')[0].strip()
                    if filename:
                        processed.add(filename)
        except Exception as e:
            print(f"Warning: Could not read existing output file: {e}")
    
    return processed


def analyse_game(pgn_path: Path, stockfish_path: str, depth: int = 20, book_path: str = None) -> GameStats:
    """
    Analyse a single PGN file with Stockfish.
    
    Args:
        pgn_path: Path to PGN file
        stockfish_path: Path to Stockfish executable
        depth: Analysis depth (higher = slower but more accurate)
        book_path: Path to Polyglot opening book (optional)
        
    Returns:
        GameStats object with analysis results
    """
    try:
        # Load the game
        with open(pgn_path) as f:
            game = chess.pgn.read_game(f)
        
        if game is None:
            return GameStats(pgn_path.name, "", "", 0, 0, "unknown", "unknown", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        
        # Get player names
        white_player = game.headers.get("White", "unknown")
        black_player = game.headers.get("Black", "unknown")

        # Get game result
        result_str = game.headers.get("Result", "*")
        if result_str == "1-0":
            result = 1  # White won
        elif result_str == "0-1":
            result = -1  # Black won
        elif result_str == "1/2-1/2":
            result = 0  # Draw
        else:
            result = 0  # Unknown/ongoing, treat as draw

        # Get opening ECO code
        opening = game.headers.get("ECO", "unknown")
        
        # Get player Elos
        white_elo = game.headers.get("WhiteElo", "0")
        black_elo = game.headers.get("BlackElo", "0")
        try:
            white_elo = int(white_elo)
            black_elo = int(black_elo)
        except ValueError:
            white_elo = 0
            black_elo = 0
        
        # Get time class from TimeControl header
        tc = game.headers.get("TimeControl", "")
        if tc and tc != "-":
            try:
                # Check for daily format (e.g., "1/86400")
                if "/" in tc:
                    time_control = "daily"
                else:
                    # Extract base time (before the +increment)
                    base_time = int(tc.split("+")[0])
                    if base_time < 180:           # 0-3 minutes
                        time_control = "bullet"
                    elif base_time <= 300:        # 3-5 minutes inclusive
                        time_control = "blitz"
                    elif base_time <= 3600:       # 5-60 minutes inclusive
                        time_control = "rapid"
                    else:                         # > 60 minutes
                        time_control = "classical"
            except (ValueError, IndexError):
                time_control = "unknown"
        else:
            time_control = "unknown"
            
        # Open opening book if provided
        book_reader = None
        if book_path and Path(book_path).exists():
            book_reader = chess.polyglot.open_reader(book_path)
        
        # Start engine
        engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
        
        # Track statistics separately for White and Black
        white_classifications = {
            'best': 0,
            'good': 0,
            'inaccuracy': 0,
            'mistake': 0,
            'blunder': 0
        }
        black_classifications = {
            'best': 0,
            'good': 0,
            'inaccuracy': 0,
            'mistake': 0,
            'blunder': 0
        }
        # Store eval pairs instead of just losses
        white_eval_pairs = []
        black_eval_pairs = []
        white_book_moves = 0
        black_book_moves = 0
        
        board = game.board()
        move_number = 0
        
        for move in game.mainline_moves():
            move_number += 1
            is_white_move = (move_number % 2 == 1)
            
            # Check if move is in opening book
            in_book = False
            if book_reader:
                try:
                    # Check if the current position has the played move in the book
                    for entry in book_reader.find_all(board):
                        if entry.move == move:
                            in_book = True
                            break
                except IndexError:
                    pass  # Position not in book
            
            # If move is in book, count it and skip engine analysis
            if in_book:
                if is_white_move:
                    white_book_moves += 1
                else:
                    black_book_moves += 1
                board.push(move)
                continue
            
            # Move not in book - analyse with engine
            # Get evaluation before the move
            info_before = engine.analyse(board, chess.engine.Limit(depth=depth))
            eval_before = get_eval_centipawns(info_before)
            
            # Make the played move
            board.push(move)
            
            # Get evaluation after the move
            info_after = engine.analyse(board, chess.engine.Limit(depth=depth))
            eval_after = info_after['score'].white().score(mate_score=10000)
            
            # Calculate evaluation loss from the player's perspective
            if is_white_move:
                eval_loss = eval_before - eval_after
            else:
                eval_loss = eval_after - eval_before
            
            eval_loss = max(0, eval_loss)  # Only count losses, not gains
            
            # Classify the move and add to appropriate player's stats
            classification = classify_move(eval_loss)
            
            if is_white_move:
                white_eval_pairs.append((eval_before, eval_after))
                white_classifications[classification] += 1
            else:
                black_eval_pairs.append((-eval_before, -eval_after))
                black_classifications[classification] += 1
        
        engine.quit()
        if book_reader:
            book_reader.close()
        
        # Calculate overall accuracy for each player using actual eval pairs
        white_accuracy = calculate_accuracy(white_eval_pairs)
        black_accuracy = calculate_accuracy(black_eval_pairs)

        return GameStats(
            filename=pgn_path.name,
            white_player=white_player,
            black_player=black_player,
            white_elo=white_elo,
            black_elo=black_elo,
            time_control=time_control,
            opening=opening,
            result=result,
            white_accuracy=round(white_accuracy, 1),
            white_best_moves=white_classifications['best'],
            white_good_moves=white_classifications['good'],
            white_inaccuracies=white_classifications['inaccuracy'],
            white_mistakes=white_classifications['mistake'],
            white_blunders=white_classifications['blunder'],
            white_book_moves=white_book_moves,
            white_total_moves=len(white_eval_pairs) + white_book_moves,
            black_accuracy=round(black_accuracy, 1),
            black_best_moves=black_classifications['best'],
            black_good_moves=black_classifications['good'],
            black_inaccuracies=black_classifications['inaccuracy'],
            black_mistakes=black_classifications['mistake'],
            black_blunders=black_classifications['blunder'],
            black_book_moves=black_book_moves,
            black_total_moves=len(black_eval_pairs) + black_book_moves
        )
        
    except Exception as e:
        print(f"Error analysing {pgn_path.name}: {e}", file=sys.stderr)
        return GameStats(pgn_path.name, "", "", 0, 0, "unknown", "unknown", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def analyse_game_wrapper(args: Tuple[Path, str, int, str]) -> GameStats:
    """Wrapper function for multiprocessing."""
    pgn_path, stockfish_path, depth, book_path = args
    return analyse_game(pgn_path, stockfish_path, depth, book_path)


def analyse_all_games(
    pgn_dir: str,
    stockfish_path: str,
    output_file: str = "analysis_results.tsv",
    depth: int = 20,
    num_processes: int = None,
    book_path: str = None
):
    """
    Analyse all PGN files in a directory using parallel processing.
    
    Args:
        pgn_dir: Directory containing PGN files
        stockfish_path: Path to Stockfish executable
        output_file: Output TSV file path
        depth: Stockfish analysis depth
        num_processes: Number of parallel processes (default: CPU count)
        book_path: Path to Polyglot opening book (optional)
    """
    # Expand user paths
    pgn_path = Path(pgn_dir).expanduser()
    stockfish_path = str(Path(stockfish_path).expanduser())
    output_file = str(Path(output_file).expanduser())
    
    if book_path:
        book_path = str(Path(book_path).expanduser())
   
    # Handling no PGN files found
    all_pgn_files = sorted(pgn_path.glob("*.pgn"))
    if not all_pgn_files:
        print(f"No PGN files found in {pgn_dir}")
        return
    
    # Load already-processed files
    processed_files = load_processed_files(output_file)
    
    if processed_files:
        print(f"Found {len(processed_files)} already-processed files in {output_file}")
    
    # Filter out already-processed files
    pgn_files = [f for f in all_pgn_files if f.name not in processed_files]
    
    if not pgn_files:
        print(f"All {len(all_pgn_files)} files have already been processed!")
        return
    
    print(f"Found {len(all_pgn_files)} total PGN files")
    print(f"Skipping {len(processed_files)} already-processed files")
    print(f"Analysing {len(pgn_files)} remaining files")
    print(f"Using depth: {depth}")
    
    if book_path:
        if Path(book_path).exists():
            print(f"Using opening book: {book_path}")
        else:
            print(f"Warning: Opening book not found at {book_path}, proceeding without book")
            book_path = None
    
    if num_processes is None:
        num_processes = mp.cpu_count() - 4
    
    print(f"Using {num_processes} parallel processes")
    print(f"Starting analysis.")
    
    # Prepare arguments for parallel processing
    args = [(pgn_file, stockfish_path, depth, book_path) for pgn_file in pgn_files]
    
    # Create output file with header if it doesn't exist
    output_path = Path(output_file)
    if not output_path.exists():
        with open(output_file, 'w') as f:
            f.write("filename\twhite_player\tblack_player\twhite_elo\tblack_elo\ttime_control\topening\tresult\t"
                    "white_accuracy\twhite_best_moves\twhite_good_moves\twhite_inaccuracies\t"
                    "white_mistakes\twhite_blunders\twhite_book_moves\twhite_total_moves\t"
                    "black_accuracy\tblack_best_moves\tblack_good_moves\tblack_inaccuracies\t"
                    "black_mistakes\tblack_blunders\tblack_book_moves\tblack_total_moves\n")

    
    # Process games in parallel with progress reporting
    with mp.Pool(processes=num_processes) as pool:
        results = []
        for i, stats in enumerate(pool.imap_unordered(analyse_game_wrapper, args), 1):
            results.append(stats)
            
            # Write result immediately
            with open(output_file, 'a') as f:
                f.write(f"{stats.filename}\t{stats.white_player}\t{stats.black_player}\t"
                       f"{stats.white_elo}\t{stats.black_elo}\t{stats.time_control}\t{stats.opening}\t{stats.result}\t"
                       f"{stats.white_accuracy}\t{stats.white_best_moves}\t{stats.white_good_moves}\t"
                       f"{stats.white_inaccuracies}\t{stats.white_mistakes}\t{stats.white_blunders}\t"
                       f"{stats.white_book_moves}\t{stats.white_total_moves}\t"
                       f"{stats.black_accuracy}\t{stats.black_best_moves}\t{stats.black_good_moves}\t"
                       f"{stats.black_inaccuracies}\t{stats.black_mistakes}\t{stats.black_blunders}\t"
                       f"{stats.black_book_moves}\t{stats.black_total_moves}\n")
            
            # Progress update
            if i % 10 == 0 or i == len(pgn_files):
                print(f"Processed {i}/{len(pgn_files)} games.")
    
    print(f"\n✓ Analysis complete! Results saved to {output_file}")



if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Analyse Chess.com PGN files with Stockfish"
    )
    parser.add_argument(
        "pgn_directory",
        help="Directory containing PGN files"
    )
    parser.add_argument(
        "stockfish_path",
        help="Path to Stockfish executable"
    )
    parser.add_argument(
        "-o", "--output",
        default="analysis_results.tsv",
        help="Output TSV file (default: analysis_results.tsv)"
    )
    parser.add_argument(
        "-d", "--depth",
        type=int,
        default=18,
        help="Stockfish analysis depth (default: 18, higher=slower but more accurate)"
    )
    parser.add_argument(
        "-p", "--processes",
        type=int,
        default=None,
        help="Number of parallel processes (default: number of CPU cores)"
    )
    parser.add_argument(
        "-b", "--book",
        default=None,
        help="Path to Polyglot opening book (.bin file)"
    )
    
    args = parser.parse_args()
    
    analyse_all_games(
        args.pgn_directory,
        args.stockfish_path,
        args.output,
        args.depth,
        args.processes,
        args.book
    )
