# prospector/server/game.py

import uuid
import time
import random
from typing import Dict, List, Tuple, Optional, Set, Any

from prospector.server.player import Player
from prospector.common.constants import (
    DEFAULT_GRID_SIZE, 
    ORIENTATION_HORIZONTAL, 
    ORIENTATION_VERTICAL,
    GAME_STATE_WAITING,
    GAME_STATE_PLAYING,
    GAME_STATE_FINISHED,
    DEFAULT_PLAYERS,
    MAX_PLAYERS,
    LAND_TYPE_REGULAR,
    LAND_TYPE_COPPER,
    LAND_TYPE_SILVER,
    LAND_TYPE_GOLD,
    LAND_VALUE_REGULAR,
    LAND_VALUE_COPPER,
    LAND_VALUE_SILVER,
    LAND_VALUE_GOLD,
    DEFAULT_TURN_TIMEOUT
)

class LandCell:
    """Represents a piece of land in the Prospector game"""
    
    def __init__(self, land_type: str = LAND_TYPE_REGULAR):
        self.type = land_type
        self.owner = None  # Index of the player who owns the cell
        self.value = self.get_value_for_type(land_type)
    
    @staticmethod
    def get_value_for_type(land_type: str) -> int:
        """Get the value for a given land type"""
        value_map = {
            LAND_TYPE_REGULAR: LAND_VALUE_REGULAR,
            LAND_TYPE_COPPER: LAND_VALUE_COPPER,
            LAND_TYPE_SILVER: LAND_VALUE_SILVER,
            LAND_TYPE_GOLD: LAND_VALUE_GOLD
        }
        return value_map.get(land_type, LAND_VALUE_REGULAR)
    
    def to_dict(self) -> Dict:
        """Convert land cell to dictionary for JSON serialization"""
        return {
            "type": self.type,
            "value": self.value,
            "owner": self.owner
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'LandCell':
        """Create a LandCell instance from dictionary data"""
        cell = cls(data.get("type", LAND_TYPE_REGULAR))
        cell.owner = data.get("owner")
        cell.value = data.get("value", LAND_VALUE_REGULAR)
        return cell

class ProspectorGame:
    """Main game logic for Prospector"""
    
    def __init__(self, grid_size: int = DEFAULT_GRID_SIZE, max_players: int = DEFAULT_PLAYERS, 
                game_id: str = None, land_config: Dict[str, float] = None, turn_timeout: int = DEFAULT_TURN_TIMEOUT):
        self.id = game_id if game_id else str(uuid.uuid4())
        self.grid_size = grid_size
        self.max_players = min(max_players, MAX_PLAYERS)  # Ensure we don't exceed MAX_PLAYERS
        self.players: List[Player] = []
        self.current_player_idx = 0
        self.state = GAME_STATE_WAITING
        self.start_time = None
        self.turn_timeout = turn_timeout  # Seconds allowed per turn
        self.turn_start_time = None
        self.game_history = []  # For recording game moves
        
        # Land configuration (percentages for each type)
        self.land_config = land_config or {
            LAND_TYPE_REGULAR: 0.7,
            LAND_TYPE_COPPER: 0.2,
            LAND_TYPE_SILVER: 0.07,
            LAND_TYPE_GOLD: 0.03
        }
        
        # Initialize the game grid
        # horizontal_fences[i][j] represents a horizontal fence at the top of cell (i,j)
        # vertical_fences[i][j] represents a vertical fence at the left of cell (i,j)
        self.horizontal_fences = [[False for _ in range(grid_size)] for _ in range(grid_size + 1)]
        self.vertical_fences = [[False for _ in range(grid_size + 1)] for _ in range(grid_size)]
        
        # Initialize land cells with types based on configuration
        self.land_cells = [[LandCell() for _ in range(grid_size)] for _ in range(grid_size)]
        self._distribute_land_types()
        
        # Number of unclaimed lands
        self.unclaimed_lands = grid_size * grid_size
    
    def _distribute_land_types(self):
        """Distribute land types across the grid based on land_config"""
        # Create a flat list of land types based on percentages
        land_types = []
        for land_type, percentage in self.land_config.items():
            count = int(self.grid_size * self.grid_size * percentage)
            land_types.extend([land_type] * count)
        
        # Fill the rest with regular land
        while len(land_types) < self.grid_size * self.grid_size:
            land_types.append(LAND_TYPE_REGULAR)
        
        # Shuffle the land types
        random.shuffle(land_types)
        
        # Distribute to the grid
        idx = 0
        for row in range(self.grid_size):
            for col in range(self.grid_size):
                self.land_cells[row][col] = LandCell(land_types[idx])
                idx += 1
    
    def add_player(self, player: Player) -> bool:
        """
        Add a player to the game
        
        Args:
            player: The player to add
            
        Returns:
            True if player was added, False if the game is full
        """
        if len(self.players) < self.max_players:
            self.players.append(player)
            
            # Start the game if we have enough players
            if len(self.players) >= 2:
                self.state = GAME_STATE_PLAYING
                self.start_time = time.time()
                self.turn_start_time = time.time()
            
            return True
        
        return False
    
    def remove_player(self, player_id: str) -> bool:
        """
        Remove a player from the game
        
        Args:
            player_id: ID of the player to remove
            
        Returns:
            True if player was removed, False if player wasn't found
        """
        for i, player in enumerate(self.players):
            if player.id == player_id:
                # If the game is in progress, other players win
                if self.state == GAME_STATE_PLAYING:
                    # Update stats for all players
                    for j, other_player in enumerate(self.players):
                        if j != i:  # Not the player who left
                            other_player.win_game()
                    player.lose_game()
                    self.state = GAME_STATE_FINISHED
                    
                    # Record the event in history
                    self.game_history.append({
                        "type": "player_left",
                        "player_id": player_id,
                        "time": time.time()
                    })
                
                self.players.pop(i)
                
                # If we only have one player left, end the game
                if len(self.players) < 2 and self.state == GAME_STATE_PLAYING:
                    self.state = GAME_STATE_FINISHED
                
                return True
        
        return False
    
    def place_fence(self, player_id: str, row: int, col: int, 
                   orientation: str) -> Tuple[bool, List[Tuple[int, int]]]:
        """
        Place a fence on the board
        
        Args:
            player_id: ID of the player making the move
            row, col: Coordinates of the fence
            orientation: Either "horizontal" or "vertical"
            
        Returns:
            Tuple containing:
            - Success flag (True if fence was placed)
            - List of land coordinates that were claimed as a result of this move
        """
        # Check if game is in playing state
        if self.state != GAME_STATE_PLAYING:
            return False, []
            
        # Check if it's this player's turn
        current_player = self.get_current_player()
        if not current_player or current_player.id != player_id:
            return False, []
        
        # Check if turn time has expired
        if self.turn_timeout > 0 and self.turn_start_time:
            elapsed = time.time() - self.turn_start_time
            if elapsed > self.turn_timeout:
                # Turn timeout - move to next player
                self.next_turn()
                return False, []
        
        # Check coordinates are valid
        if orientation == ORIENTATION_HORIZONTAL:
            if not (0 <= row <= self.grid_size and 0 <= col < self.grid_size):
                return False, []
            # Check if fence already exists
            if self.horizontal_fences[row][col]:
                return False, []
            # Place the fence
            self.horizontal_fences[row][col] = True
        
        elif orientation == ORIENTATION_VERTICAL:
            if not (0 <= row < self.grid_size and 0 <= col <= self.grid_size):
                return False, []
            # Check if fence already exists
            if self.vertical_fences[row][col]:
                return False, []
            # Place the fence
            self.vertical_fences[row][col] = True
        
        else:
            # Invalid orientation
            return False, []
        
        # Update player's last active time
        current_player.update_activity()
        
        # Record the move in history
        self.game_history.append({
            "type": "fence_placed",
            "player_id": player_id,
            "row": row,
            "col": col,
            "orientation": orientation,
            "time": time.time()
        })
        
        # Check if any land was claimed
        claimed_land = self.check_claimed_land()
        
        # If land was claimed, player gets to move again; otherwise, next player's turn
        if not claimed_land:
            self.next_turn()
        else:
            # Update score for claimed land
            score_gained = 0
            for row, col in claimed_land:
                land_cell = self.land_cells[row][col]
                land_cell.owner = self.current_player_idx
                score_gained += land_cell.value
            
            current_player.add_score(score_gained)
            
            # Update unclaimed lands
            self.unclaimed_lands -= len(claimed_land)
            
            # Record the claim in history
            self.game_history.append({
                "type": "land_claimed",
                "player_id": player_id,
                "lands": claimed_land,
                "score_gained": score_gained,
                "time": time.time()
            })
            
            # Check if game is over
            if self.unclaimed_lands == 0:
                self.end_game()
        
        # Reset turn timer
        self.turn_start_time = time.time()
        
        return True, claimed_land
    
    def check_claimed_land(self) -> List[Tuple[int, int]]:
        """
        Check if any land has been claimed due to the latest move
        
        Returns:
            List of (row, col) coordinates of newly claimed land
        """
        claimed = []
        
        # Check each unclaimed land cell
        for row in range(self.grid_size):
            for col in range(self.grid_size):
                if self.land_cells[row][col].owner is None:
                    # Check if this land is now enclosed by fences
                    if (self.horizontal_fences[row][col] and      # Top fence
                        self.horizontal_fences[row+1][col] and    # Bottom fence
                        self.vertical_fences[row][col] and        # Left fence
                        self.vertical_fences[row][col+1]):        # Right fence
                        
                        claimed.append((row, col))
        
        return claimed
    
    def get_current_player(self) -> Optional[Player]:
        """Get the player whose turn it is"""
        if not self.players or self.current_player_idx >= len(self.players):
            return None
        return self.players[self.current_player_idx]
    
    def next_turn(self):
        """Advance to the next player's turn"""
        if self.players:
            self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
            self.turn_start_time = time.time()
    
    def check_inactivity(self) -> bool:
        """
        Check if the current player has been inactive for too long
        
        Returns:
            True if the player is inactive and was removed, False otherwise
        """
        if self.state != GAME_STATE_PLAYING or not self.turn_start_time:
            return False
        
        current_player = self.get_current_player()
        if not current_player:
            return False
        
        # Check if turn time has expired
        elapsed = time.time() - self.turn_start_time
        if elapsed > self.turn_timeout:
            # Player inactive - remove them
            self.remove_player(current_player.id)
            return True
        
        return False
    
    def end_game(self):
        """End the game and update player statistics"""
        if self.state == GAME_STATE_FINISHED:
            return
            
        self.state = GAME_STATE_FINISHED
        
        # Record game end in history
        self.game_history.append({
            "type": "game_over",
            "time": time.time()
        })
        
        # Determine winner based on score
        if len(self.players) < 2:
            # Only one player left, they win by default
            if self.players:
                self.players[0].win_game()
            return
        
        # Find player with highest score
        max_score = -1
        winners = []
        
        for i, player in enumerate(self.players):
            if player.score > max_score:
                max_score = player.score
                winners = [i]
            elif player.score == max_score:
                winners.append(i)
        
        if len(winners) == 1:
            # Single winner
            winner_idx = winners[0]
            self.players[winner_idx].win_game()
            
            # Everyone else loses
            for i, player in enumerate(self.players):
                if i != winner_idx:
                    player.lose_game()
        else:
            # Multiple winners (draw)
            for i in winners:
                self.players[i].draw_game()
            
            # Everyone else loses
            for i, player in enumerate(self.players):
                if i not in winners:
                    player.lose_game()
    
    def get_replay(self) -> List[Dict]:
        """Get the game history for replay"""
        return self.game_history
    
    def get_land_value(self, row: int, col: int) -> int:
        """Get the value of a land cell"""
        if 0 <= row < self.grid_size and 0 <= col < self.grid_size:
            return self.land_cells[row][col].value
        return 0
    
    def get_land_type(self, row: int, col: int) -> str:
        """Get the type of a land cell"""
        if 0 <= row < self.grid_size and 0 <= col < self.grid_size:
            return self.land_cells[row][col].type
        return LAND_TYPE_REGULAR
    
    def to_dict(self) -> Dict:
        """Convert game state to dictionary for JSON serialization"""
        # Convert land cells to dict
        land_cells_dict = []
        for row in range(self.grid_size):
            row_dict = []
            for col in range(self.grid_size):
                row_dict.append(self.land_cells[row][col].to_dict())
            land_cells_dict.append(row_dict)
            
        return {
            "id": self.id,
            "grid_size": self.grid_size,
            "max_players": self.max_players,
            "state": self.state,
            "current_player_id": self.get_current_player().id if self.get_current_player() else None,
            "players": [player.to_dict() for player in self.players],
            "horizontal_fences": self.horizontal_fences,
            "vertical_fences": self.vertical_fences,
            "land_cells": land_cells_dict,
            "unclaimed_lands": self.unclaimed_lands,
            "turn_timeout": self.turn_timeout,
            "turn_start_time": self.turn_start_time,
            "game_time": time.time() - self.start_time if self.start_time else 0
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ProspectorGame':
        """Create a ProspectorGame instance from dictionary data"""
        game = cls(
            grid_size=data.get("grid_size", DEFAULT_GRID_SIZE),
            max_players=data.get("max_players", DEFAULT_PLAYERS),
            game_id=data.get("id"),
            turn_timeout=data.get("turn_timeout", DEFAULT_TURN_TIMEOUT)
        )
        
        game.state = data.get("state", GAME_STATE_WAITING)
        game.unclaimed_lands = data.get("unclaimed_lands", game.grid_size * game.grid_size)
        game.turn_start_time = data.get("turn_start_time")
        game.start_time = time.time() - data.get("game_time", 0) if game.state != GAME_STATE_WAITING else None
        
        # Restore players
        for player_data in data.get("players", []):
            player = Player.from_dict(player_data)
            game.players.append(player)
        
        # Set current player
        current_player_id = data.get("current_player_id")
        if current_player_id:
            for i, player in enumerate(game.players):
                if player.id == current_player_id:
                    game.current_player_idx = i
                    break
        
        # Restore fences
        game.horizontal_fences = data.get("horizontal_fences", game.horizontal_fences)
        game.vertical_fences = data.get("vertical_fences", game.vertical_fences)
        
        # Restore land cells
        land_cells_data = data.get("land_cells")
        if land_cells_data:
            for row in range(min(len(land_cells_data), game.grid_size)):
                for col in range(min(len(land_cells_data[row]), game.grid_size)):
                    game.land_cells[row][col] = LandCell.from_dict(land_cells_data[row][col])
        
        return game