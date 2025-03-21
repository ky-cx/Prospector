# prospector/server/game_recorder.py

import json
import os
import time
from typing import Dict, List, Optional, Any

from prospector.common.constants import DEFAULT_RECORDS_DIR, GAME_RECORD_EXTENSION

class GameRecorder:
    """Records and replays games"""
    
    def __init__(self, records_dir: str = DEFAULT_RECORDS_DIR):
        self.records_dir = records_dir
        
        # Create records directory if it doesn't exist
        os.makedirs(records_dir, exist_ok=True)
    
    def save_game(self, game_id: str, game_data: Dict, filename: str = None) -> str:
        """
        Save a game to disk
        
        Args:
            game_id: ID of the game
            game_data: Game data to save
            filename: Optional filename, will be generated if not provided
            
        Returns:
            Path to the saved file
        """
        # Generate filename if not provided
        if not filename:
            timestamp = int(time.time())
            filename = f"game_{game_id}_{timestamp}{GAME_RECORD_EXTENSION}"
        
        # Add extension if not present
        if not filename.endswith(GAME_RECORD_EXTENSION):
            filename += GAME_RECORD_EXTENSION
        
        # Create full path
        file_path = os.path.join(self.records_dir, filename)
        
        # Save game data
        with open(file_path, 'w') as f:
            json.dump(game_data, f, indent=2)
        
        return filename
    
    def load_game(self, filename: str) -> Optional[Dict]:
        """
        Load a game from disk
        
        Args:
            filename: Name of the file to load
            
        Returns:
            Game data if successful, None otherwise
        """
        # Add extension if not present
        if not filename.endswith(GAME_RECORD_EXTENSION):
            filename += GAME_RECORD_EXTENSION
        
        # Create full path
        file_path = os.path.join(self.records_dir, filename)
        
        # Check if file exists
        if not os.path.exists(file_path):
            return None
        
        # Load game data
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading game: {e}")
            return None
    
    def list_saved_games(self) -> List[Dict]:
        """
        List all saved games
        
        Returns:
            List of game info dictionaries
        """
        games = []
        
        # Iterate through files in records directory
        for filename in os.listdir(self.records_dir):
            if filename.endswith(GAME_RECORD_EXTENSION):
                file_path = os.path.join(self.records_dir, filename)
                
                try:
                    # Get file info
                    stat = os.stat(file_path)
                    
                    # Try to load basic game info
                    game_info = {
                        "filename": filename,
                        "size": stat.st_size,
                        "created": stat.st_ctime,
                        "modified": stat.st_mtime
                    }
                    
                    # Try to load more detailed info from the file
                    try:
                        with open(file_path, 'r') as f:
                            data = json.load(f)
                            
                            # Extract basic game info
                            if "game_info" in data:
                                game_info.update(data["game_info"])
                    except:
                        pass
                    
                    games.append(game_info)
                    
                except Exception as e:
                    print(f"Error loading game info for {filename}: {e}")
        
        # Sort by creation time, newest first
        games.sort(key=lambda g: g["created"], reverse=True)
        
        return games
    
    def delete_game(self, filename: str) -> bool:
        """
        Delete a saved game
        
        Args:
            filename: Name of the file to delete
            
        Returns:
            Success flag
        """
        # Add extension if not present
        if not filename.endswith(GAME_RECORD_EXTENSION):
            filename += GAME_RECORD_EXTENSION
        
        # Create full path
        file_path = os.path.join(self.records_dir, filename)
        
        # Check if file exists
        if not os.path.exists(file_path):
            return False
        
        # Delete file
        try:
            os.remove(file_path)
            return True
        except Exception as e:
            print(f"Error deleting game: {e}")
            return False
    
    def format_game_for_replay(self, game_data: Dict) -> Dict:
        """
        Format game data for replay
        
        Args:
            game_data: Raw game data
            
        Returns:
            Formatted game data for replay
        """
        # Extract game history
        history = game_data.get("history", [])
        
        # Extract game info
        game_info = {
            "id": game_data.get("id", "unknown"),
            "grid_size": game_data.get("grid_size", 5),
            "max_players": game_data.get("max_players", 2),
            "players": game_data.get("players", []),
            "start_time": game_data.get("start_time"),
            "end_time": game_data.get("end_time")
        }
        
        return {
            "game_info": game_info,
            "history": history
        }