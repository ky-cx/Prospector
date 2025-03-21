# prospector/server/player.py

import uuid
import time
from typing import Dict, List, Optional

class Player:
    """Represents a player in the Prospector game"""
    
    def __init__(self, name: str, player_id: str = None):
        self.name = name
        self.id = player_id if player_id else str(uuid.uuid4())
        self.score = 0
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.last_active = time.time()
        self.games_played = 0
    
    def update_activity(self):
        """Update the last active timestamp"""
        self.last_active = time.time()
    
    def win_game(self):
        """Update stats when player wins a game"""
        self.wins += 1
        self.games_played += 1
    
    def lose_game(self):
        """Update stats when player loses a game"""
        self.losses += 1
        self.games_played += 1
    
    def draw_game(self):
        """Update stats when player draws a game"""
        self.draws += 1
        self.games_played += 1
    
    def reset_score(self):
        """Reset the score for a new game"""
        self.score = 0
    
    def add_score(self, points: int):
        """Add points to player's score"""
        self.score += points
    
    def to_dict(self) -> Dict:
        """Convert player to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "stats": {
                "wins": self.wins,
                "losses": self.losses,
                "draws": self.draws,
                "games_played": self.games_played
            },
            "last_active": self.last_active
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Player':
        """Create a Player instance from dictionary data"""
        player = cls(data.get("name", "Unknown"))
        player.id = data.get("id", str(uuid.uuid4()))
        player.score = data.get("score", 0)
        
        stats = data.get("stats", {})
        player.wins = stats.get("wins", 0)
        player.losses = stats.get("losses", 0)
        player.draws = stats.get("draws", 0)
        player.games_played = stats.get("games_played", 0)
        
        player.last_active = data.get("last_active", time.time())
        
        return player