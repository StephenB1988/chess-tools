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
        "User-Agent": f"@StephenB1988:chess-tools/1.0 (contact: {email})"
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


def get_existing_files_by_month(output_dir: str) -> dict:
    """
    Get existing files grouped by year-month.
    
    Args:
        output_dir: Directory containing PGN files
        
    Returns:
        Dict mapping 'YYYY-MM' to set of filenames from that month
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        return {}
    
    files_by_month = {}
    
    for pgn_file in output_path.glob("*.pgn"):
        # Extract year-month from filename (YYYY-MM-DD_HHMM_...)
        try:
            year_month = pgn_file.name[:7]  # First 7 chars: "YYYY-MM"
            if year_month not in files_by_month:
                files_by_month[year_month] = set()
            files_by_month[year_month].add(pgn_file.name)
        except:
            pass  # Skip malformed filenames
    
    return files_by_month


def export_games(username: str, email: str, output_dir: str = "chess_games"):
    """
    Export all games for a Chess.com user as individual PGN files.
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Get existing files grouped by month
    files_by_month = get_existing_files_by_month(output_dir)
    all_existing_files = set()
    for month_files in files_by_month.values():
        all_existing_files.update(month_files)
    
    if all_existing_files:
        print(f"Found {len(all_existing_files)} existing files across {len(files_by_month)} months")
    
    print(f"Fetching game archives for user: {username}")
    
    try:
        archives = get_game_archives(username, email)
        print(f"Found {len(archives)} monthly archives")
        
        total_games = 0
        skipped_games = 0
        skipped_months = 0
        
        for i, archive_url in enumerate(archives, 1):
            # Extract year-month from URL (e.g., .../2025/11)
            try:
                url_parts = archive_url.rstrip('/').split('/')
                year_month = f"{url_parts[-2]}-{url_parts[-1]}"
            except:
                year_month = None
            
            # Quick check: if this month has no files, we need to fetch
            # If it has files, we still need to fetch to check for new games
            # But we can skip if the month is "complete" (you'd need to define this)
            
            print(f"\nProcessing archive {i}/{len(archives)}: {archive_url}")
            if year_month and year_month in files_by_month:
                print(f"  (Month {year_month} has {len(files_by_month[year_month])} existing files)")
            
            try:
                games = get_games_from_archive(archive_url, email)
                print(f"  Found {len(games)} games in archive")
                
                # Check if all games from this archive already exist
                month_new_games = 0
                month_skipped = 0
                
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
                    
                    # Create filename
                    filename = sanitize_filename(f"{date_str}_{white}_vs_{black}.pgn")
                    
                    # Skip if file already exists
                    if filename in all_existing_files:
                        month_skipped += 1
                        skipped_games += 1
                        continue
                    
                    # Save PGN to file
                    file_path = output_path / filename
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(pgn)
                    
                    month_new_games += 1
                    total_games += 1
                
                # If we found no new games this month, note it
                if month_new_games == 0 and len(games) > 0:
                    print(f"  All {len(games)} games already downloaded")
                elif month_new_games > 0:
                    print(f"  Downloaded {month_new_games} new games, skipped {month_skipped}")
                
                # Be polite to the API
                if i < len(archives):
                    time.sleep(0.5)
                    
            except requests.exceptions.RequestException as e:
                print(f"  Error fetching archive: {e}")
                continue
        
        print(f"\n✓ Export complete!")
        print(f"  Saved {total_games} new games")
        print(f"  Skipped {skipped_games} already-downloaded games")
        print(f"  Total files in {output_dir}/: {total_games + len(all_existing_files)}")
        
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
