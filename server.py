# prospector/server/server.py

import socket
import threading
import json
import logging
import time
from typing import Dict, List, Optional

from prospector.common.constants import DEFAULT_PORT, DEFAULT_HOST, BUFFER_SIZE
from prospector.common.protocol import Protocol, ClientMessageType, ServerMessageType
from prospector.server.game import ProspectorGame
from prospector.server.player import Player

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ProspectorServer")

class ProspectorServer:
    """
    Server for the Prospector game, handling client connections and game state
    """
    
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.clients = {}  # Maps client_socket to (player_id, game_id)
        self.games: Dict[str, ProspectorGame] = {}  # Maps game_id to game object
        self.players: Dict[str, Player] = {}  # Maps player_id to player object
        
        # Lock for thread safety when modifying shared data
        self.lock = threading.Lock()
    
    def start_timer_thread(self):
        """Start a thread to handle turn timers"""
        timer_thread = threading.Thread(target=self.check_turn_timers)
        timer_thread.daemon = True
        timer_thread.start()
    
    def check_turn_timers(self):
        """Periodically check turn timers and send updates to clients"""
        while self.running:
            time.sleep(1)  # Check every second
            
            with self.lock:
                # Check each game
                for game_id, game in list(self.games.items()):
                    if game.state != "playing" or not game.turn_start_time:
                        continue
                    
                    # Get current player
                    current_player = game.get_current_player()
                    if not current_player:
                        continue
                    
                    # Calculate time left
                    elapsed = time.time() - game.turn_start_time
                    time_left = max(0, game.turn_timeout - elapsed)
                    
                    # Send timer update to players
                    timer_message = Protocol.turn_timer_response(
                        game_id=game.id,
                        time_left=int(time_left),
                        player_id=current_player.id
                    )
                    
                    # Find all clients for this game
                    for client_socket, (player_id, game_id_check) in list(self.clients.items()):
                        if game_id_check == game.id:
                            try:
                                client_socket.sendall(timer_message.encode('utf-8'))
                            except Exception as e:
                                logger.error(f"Error sending timer to client: {e}")
                    
                    # If time is running out (less than 10 seconds), send warning
                    if 0 < time_left < 10:
                        warning_message = Protocol.inactive_warning_response(
                            game_id=game.id,
                            time_left=int(time_left),
                            player_id=current_player.id
                        )
                        
                        # Send warning to current player
                        for client_socket, (player_id, game_id_check) in list(self.clients.items()):
                            if game_id_check == game.id and player_id == current_player.id:
                                try:
                                    client_socket.sendall(warning_message.encode('utf-8'))
                                except Exception as e:
                                    logger.error(f"Error sending warning to client: {e}")
                    
                    # If time is up, handle inactivity
                    if time_left <= 0:
                        game.check_inactivity()
    
    def start(self):
        """Start the server"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)  # Queue up to 5 connection requests
            self.running = True
            
            logger.info(f"Server started on {self.host}:{self.port}")
            
            # Start a thread to monitor inactive players
            inactivity_thread = threading.Thread(target=self.check_inactive_players)
            inactivity_thread.daemon = True
            inactivity_thread.start()
            
            # Start the timer thread
            self.start_timer_thread()
            
            # Accept client connections
            while self.running:
                client_socket, address = self.socket.accept()
                logger.info(f"New connection from {address}")
                
                # Start a new thread to handle this client
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address)
                )
                client_thread.daemon = True
                client_thread.start()
                
        except Exception as e:
            logger.error(f"Error starting server: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.socket:
            self.socket.close()
        logger.info("Server stopped")
    
    def handle_client(self, client_socket: socket.socket, address):
        """
        Handle communication with a client
        
        Args:
            client_socket: Socket connected to the client
            address: Client's address information
        """
        try:
            while self.running:
                # Receive data from the client
                data = client_socket.recv(BUFFER_SIZE)
                if not data:
                    # Client disconnected
                    self.handle_client_disconnect(client_socket)
                    break
                
                # Process the received message
                message = data.decode('utf-8')
                response = self.process_message(message, client_socket)
                
                # Send response back to client
                if response:
                    client_socket.sendall(response.encode('utf-8'))
                
        except Exception as e:
            logger.error(f"Error handling client {address}: {e}")
        finally:
            self.handle_client_disconnect(client_socket)
            client_socket.close()
    
    def handle_client_disconnect(self, client_socket: socket.socket):
        """
        Handle client disconnection
        
        Args:
            client_socket: Socket of the disconnected client
        """
        with self.lock:
            if client_socket in self.clients:
                player_id, game_id = self.clients[client_socket]
                
                # Remove player from game
                if game_id in self.games:
                    game = self.games[game_id]
                    game.remove_player(player_id)
                    
                    # Update other players in the game
                    self.broadcast_game_state(game)
                    
                    # Remove game if empty
                    if not game.players:
                        del self.games[game_id]
                
                # Remove client from tracking
                del self.clients[client_socket]
                logger.info(f"Client disconnected, player_id={player_id}, game_id={game_id}")
    
    def process_message(self, message: str, client_socket: socket.socket) -> str:
        """
        Process a message received from a client
        
        Args:
            message: The message received
            client_socket: Socket connected to the client
            
        Returns:
            Response message to send back to the client
        """
        try:
            data = Protocol.parse_message(message)
            
            if "type" not in data:
                return Protocol.error_response("Invalid message format")
            
            message_type = data["type"]
            
            # Process message based on type
            if message_type == ClientMessageType.CREATE_GAME:
                return self.handle_create_game(data, client_socket)
                
            elif message_type == ClientMessageType.JOIN_GAME:
                return self.handle_join_game(data, client_socket)
                
            elif message_type == ClientMessageType.PLACE_FENCE:
                return self.handle_place_fence(data, client_socket)
                
            elif message_type == ClientMessageType.LEAVE_GAME:
                return self.handle_leave_game(data, client_socket)
                
            elif message_type == ClientMessageType.GET_GAME_STATE:
                return self.handle_get_game_state(data, client_socket)
                
            else:
                return Protocol.error_response(f"Unknown message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return Protocol.error_response(f"Server error: {str(e)}")
    
    def handle_create_game(self, data: Dict, client_socket: socket.socket) -> str:
        """Handle a request to create a new game"""
        with self.lock:
            player_name = data.get("player_name", "Player")
            grid_size = data.get("grid_size", 5)
            
            # Create player
            player = Player(player_name)
            self.players[player.id] = player
            
            # Create game
            game = ProspectorGame(grid_size=grid_size)
            game.add_player(player)
            self.games[game.id] = game
            
            # Associate client with player and game
            self.clients[client_socket] = (player.id, game.id)
            
            logger.info(f"Game created: id={game.id}, player={player_name}, size={grid_size}")
            
            return Protocol.game_created_response(
                game_id=game.id,
                player_id=player.id,
                grid_size=grid_size,
                max_players=2,
                turn_timeout=60
            )
    
    def handle_join_game(self, data: Dict, client_socket: socket.socket) -> str:
        """Handle a request to join an existing game"""
        with self.lock:
            game_id = data.get("game_id")
            player_name = data.get("player_name", "Player")
            
            if not game_id or game_id not in self.games:
                return Protocol.error_response("Game not found")
            
            game = self.games[game_id]
            
            # Create player
            player = Player(player_name)
            self.players[player.id] = player
            
            # Try to add player to game
            if not game.add_player(player):
                return Protocol.error_response("Game is full")
            
            # Associate client with player and game
            self.clients[client_socket] = (player.id, game_id)
            
            logger.info(f"Player joined: game={game_id}, player={player_name}")
            
            # Notify all players in the game
            self.broadcast_game_state(game)
            
            return Protocol.game_joined_response(
                game_id=game.id,
                player_id=player.id,
                grid_size=game.grid_size,
                max_players=game.max_players,
                players=[p.to_dict() for p in game.players],
                turn_timeout=game.turn_timeout
            )
    
    def handle_place_fence(self, data: Dict, client_socket: socket.socket) -> str:
        """Handle a request to place a fence"""
        with self.lock:
            game_id = data.get("game_id")
            player_id = data.get("player_id")
            row = data.get("row")
            col = data.get("col")
            orientation = data.get("orientation")
            
            if None in (game_id, player_id, row, col, orientation):
                return Protocol.error_response("Missing required fields")
            
            if game_id not in self.games:
                return Protocol.error_response("Game not found")
            
            game = self.games[game_id]
            
            # Check if it's this player's turn
            if game.get_current_player().id != player_id:
                return Protocol.error_response("Not your turn")
            
            # Place the fence
            success, claimed_land = game.place_fence(player_id, row, col, orientation)
            
            if not success:
                return Protocol.error_response("Invalid move")
            
            logger.info(f"Fence placed: game={game_id}, player={player_id}, position=({row},{col}), orientation={orientation}")
            
            # Notify all players in the game
            self.broadcast_game_state(game)
            
            # Calculate score gained
            score_gained = 0
            for land_row, land_col in claimed_land:
                score_gained += game.get_land_value(land_row, land_col)
            
            return Protocol.fence_placed_response(
                game_id=game_id,
                player_id=player_id,
                row=row,
                col=col,
                orientation=orientation,
                land_claimed=claimed_land,
                score_gained=score_gained
            )
    
    def handle_leave_game(self, data: Dict, client_socket: socket.socket) -> str:
        """Handle a request to leave a game"""
        with self.lock:
            game_id = data.get("game_id")
            player_id = data.get("player_id")
            
            if None in (game_id, player_id):
                return Protocol.error_response("Missing required fields")
            
            if game_id not in self.games:
                return Protocol.error_response("Game not found")
            
            game = self.games[game_id]
            
            # Remove player from game
            if not game.remove_player(player_id):
                return Protocol.error_response("Player not in game")
            
            # Remove client from tracking
            if client_socket in self.clients:
                del self.clients[client_socket]
            
            logger.info(f"Player left: game={game_id}, player={player_id}")
            
            # Notify remaining players
            self.broadcast_game_state(game)
            
            # Remove game if empty
            if not game.players:
                del self.games[game_id]
            
            return Protocol.create_server_message(
                ServerMessageType.GAME_STATE,
                status="left",
                game_id=game_id
            )
    
    def handle_get_game_state(self, data: Dict, client_socket: socket.socket) -> str:
        """Handle a request to get the current game state"""
        with self.lock:
            game_id = data.get("game_id")
            
            if not game_id or game_id not in self.games:
                return Protocol.error_response("Game not found")
            
            game = self.games[game_id]
            
            return Protocol.game_state_response(
                game_id=game.id,
                grid=self.format_grid_for_client(game),
                current_player=game.get_current_player().id if game.get_current_player() else None,
                scores={p.id: p.score for p in game.players},
                players=[p.to_dict() for p in game.players],
                turn_time_left=self.calculate_turn_time_left(game),
                land_cells=[[cell.to_dict() for cell in row] for row in game.land_cells] if hasattr(game, 'land_cells') else None
            )
    
    def calculate_turn_time_left(self, game):
        """Calculate the time left in the current turn"""
        if not game.turn_start_time or not game.turn_timeout:
            return None
        
        elapsed = time.time() - game.turn_start_time
        return max(0, int(game.turn_timeout - elapsed))
    
    def broadcast_game_state(self, game: ProspectorGame):
        """
        Send the current game state to all players in the game
        
        Args:
            game: The game whose state should be broadcast
        """
        game_state = Protocol.game_state_response(
            game_id=game.id,
            grid=self.format_grid_for_client(game),
            current_player=game.get_current_player().id if game.get_current_player() else None,
            scores={p.id: p.score for p in game.players},
            players=[p.to_dict() for p in game.players],
            turn_time_left=self.calculate_turn_time_left(game),
            land_cells=[[cell.to_dict() for cell in row] for row in game.land_cells] if hasattr(game, 'land_cells') else None
        )
        
        # Find all clients for this game
        for client_socket, (player_id, game_id) in list(self.clients.items()):
            if game_id == game.id:
                try:
                    client_socket.sendall(game_state.encode('utf-8'))
                except Exception as e:
                    logger.error(f"Error sending to client: {e}")
                    # Don't disconnect here, let the socket error handler do it
    
    def format_grid_for_client(self, game: ProspectorGame) -> List:
        """
        Format the game grid for sending to clients
        
        Args:
            game: The game whose grid should be formatted
            
        Returns:
            List representing the game grid with fences and claimed land
        """
        grid = []
        
        # Create a grid representation with all information
        for row in range(game.grid_size):
            grid_row = []
            for col in range(game.grid_size):
                # Check if we're using the new game model with land cells
                if hasattr(game, 'land_cells') and game.land_cells:
                    cell = {
                        "top_fence": game.horizontal_fences[row][col],
                        "bottom_fence": game.horizontal_fences[row+1][col],
                        "left_fence": game.vertical_fences[row][col],
                        "right_fence": game.vertical_fences[row][col+1],
                        "owner": game.land_cells[row][col].owner
                    }
                else:
                    # Fallback for old game model
                    cell = {
                        "top_fence": game.horizontal_fences[row][col],
                        "bottom_fence": game.horizontal_fences[row+1][col],
                        "left_fence": game.vertical_fences[row][col],
                        "right_fence": game.vertical_fences[row][col+1],
                        "owner": game.claimed_lands[row][col] if hasattr(game, 'claimed_lands') else None
                    }
                grid_row.append(cell)
            grid.append(grid_row)
        
        return grid
    
    def check_inactive_players(self):
        """
        Periodically check for inactive players and remove them from games
        """
        INACTIVITY_TIMEOUT = 60  # 60 seconds of inactivity
        
        while self.running:
            time.sleep(10)  # Check every 10 seconds
            
            with self.lock:
                current_time = time.time()
                
                # Check each game
                for game_id, game in list(self.games.items()):
                    if game.state != "playing":
                        continue
                    
                    # Get current player
                    current_player = game.get_current_player()
                    if not current_player:
                        continue
                    
                    # Check if current player is inactive
                    if hasattr(game, 'check_inactivity'):
                        # Use the game's built-in inactivity check if available
                        if game.check_inactivity():
                            # Game has handled the inactivity
                            continue
                    
                    # Fallback inactivity check
                    if (current_time - current_player.last_active) > INACTIVITY_TIMEOUT:
                        logger.info(f"Player {current_player.id} inactive, removing from game {game_id}")
                        
                        # Find opponent
                        opponent_idx = 1 - game.current_player_idx
                        
                        # Update stats
                        if opponent_idx < len(game.players):
                            game.players[opponent_idx].wins += 1
                            current_player.losses += 1
                        
                        # Remove player from game
                        game.remove_player(current_player.id)
                        
                        # End the game
                        game.state = "finished"
                        
                        # Notify remaining players
                        self.broadcast_game_state(game)
                        
                        # Remove game if empty
                        if not game.players:
                            del self.games[game_id]