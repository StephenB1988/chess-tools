"""
Export all games from a Chess.com user as individual PGN files.
"""

import requests
import time
import json
from pathlib import Path
from typing import List, Dict
from datetime import datetime


def get_game_archives(username: str, email: str) -> List[str]:
    """
    Get list of monthly archive URLs for a user.
    
    Args:
        username: Chess.com username
        email: Email to let chess.com know who is using their API (polite)
        
    Returns:
        List of archive URLs
    """
    url = f"https://api.chess.com/pub/player/{username}/games/archives"
    headers = {
        "User-Agent": f"@stephenbanniter:chess-tools/1.0 (contact: {email})"
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    data = response.json()
    return data.get("archives", [])


def get_games_from_archive(archive_url: str, email: str) -> List[Dict]:
    """
    Get all games from a monthly archive.
    
    Args:
        archive_url: URL to the monthly archive
        
    Returns:
        List of game dictionaries
    """
    headers = {
        "User-Agent": f"ChesscomPGNExporter/1.1 (contact: {email})"
    }
    
    response = requests.get(archive_url, headers=headers)
    response.raise_for_status()
    
    data = response.json()
    return data.get("games", [])


def sanitize_filename(text: str) -> str:
    """
    Remove characters that aren't safe for filenames.
    
    Args:
        text: Input text
        
    Returns:
        Sanitized text safe for filenames
    """
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        text = text.replace(char, '_')
    return text


def get_existing_files(output_dir: str) -> set:
    """
    Get set of already-downloaded filenames.
    
    Args:
        output_dir: Directory containing PGN files
        
    Returns:
        Set of filenames that already exist
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        return set()
    
    return {f.name for f in output_path.glob("*.pgn")}


def export_games(username: str, email: str, output_dir: str = "chess_games"):
    """
    Export all games for a Chess.com user as individual PGN files.
    
    Args:
        username: Chess.com username
        email: Email to let chess.com know who is using their API (polite)
        output_dir: Directory to save PGN files
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Get existing files to skip
    existing_files = get_existing_files(output_dir)
    
    if existing_files:
        print(f"Found {len(existing_files)} existing files in {output_dir}")
    
    print(f"Fetching game archives for user: {username}")
    print(f"Signing API requests with email: {email}")
    
    try:
        archives = get_game_archives(username, email)
        print(f"Found {len(archives)} monthly archives")
        
        total_games = 0
        skipped_games = 0
        
        for i, archive_url in enumerate(archives, 1):
            print(f"\nProcessing archive {i}/{len(archives)}: {archive_url}")
            
            try:
                games = get_games_from_archive(archive_url, email)
                print(f"  Found {len(games)} games in this archive")
                
                for game in games:
                    pgn = game.get("pgn", "")
                    if not pgn:
                        continue
                    
                    # Extract game info for filename
                    white = game.get("white", {}).get("username", "unknown")
                    black = game.get("black", {}).get("username", "unknown")
                    end_time = game.get("end_time", 0)
                    
                    # Convert timestamp to readable date/time
                    dt = datetime.fromtimestamp(end_time)
                    date_str = dt.strftime("%Y-%m-%d_%H%M")
                    
                    # Create filename: YYYY-MM-DD_HHMM_White_vs_Black.pgn
                    filename = sanitize_filename(
                        f"{date_str}_{white}_vs_{black}.pgn"
                    )
                    
                    # Skip if file already exists
                    if filename in existing_files:
                        skipped_games += 1
                        continue
                    
                    # Save PGN to file
                    file_path = output_path / filename
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(pgn)
                    
                    total_games += 1
                
                # Be polite to the API - small delay between archives
                if i < len(archives):
                    time.sleep(0.5)
                    
            except requests.exceptions.RequestException as e:
                print(f"  Error fetching archive: {e}")
                continue
        
        print(f"\n✓ Export complete!")
        print(f"  Saved {total_games} new games")
        print(f"  Skipped {skipped_games} already-downloaded games")
        print(f"  Total files in {output_dir}/: {total_games + len(existing_files)}")
        
    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to fetch archives for user '{username}'")
        print(f"  {e}")
        return


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python chesscom_pgn_export.py <username> <email> [output_directory]")
        print("\nExample:")
        print("  python chesscom_pgn_export.py user@email.com hikaru")
        print("  python chesscom_pgn_export.py user@email.com hikaru ~/pgn_files")
        sys.exit(1)
    
    username = sys.argv[1]
    email = sys.argv[2]
    output_dir = Path(sys.argv[3]).expanduser() if len(sys.argv) > 3 else "pgn_files"

    export_games(username, email, output_dir)
