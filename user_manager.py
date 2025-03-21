# prospector/server/user_manager.py

import uuid
import json
import hashlib
import os
import time
from typing import Dict, List, Optional, Tuple

class User:
    """Represents a registered user in the Prospector game"""
    
    def __init__(self, username: str, user_id: str = None):
        self.username = username
        self.id = user_id if user_id else str(uuid.uuid4())
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.games_played = 0
        self.last_login = time.time()
        self.is_logged_in = False
    
    def login(self):
        """Mark user as logged in"""
        self.is_logged_in = True
        self.last_login = time.time()
    
    def logout(self):
        """Mark user as logged out"""
        self.is_logged_in = False
    
    def add_win(self):
        """Add a win to user stats"""
        self.wins += 1
        self.games_played += 1
    
    def add_loss(self):
        """Add a loss to user stats"""
        self.losses += 1
        self.games_played += 1
    
    def add_draw(self):
        """Add a draw to user stats"""
        self.draws += 1
        self.games_played += 1
    
    def to_dict(self) -> Dict:
        """Convert user to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "username": self.username,
            "stats": {
                "wins": self.wins,
                "losses": self.losses,
                "draws": self.draws,
                "games_played": self.games_played
            },
            "last_login": self.last_login,
            "is_logged_in": self.is_logged_in
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'User':
        """Create a User instance from dictionary data"""
        user = cls(data.get("username", "Unknown"))
        user.id = data.get("id", str(uuid.uuid4()))
        
        stats = data.get("stats", {})
        user.wins = stats.get("wins", 0)
        user.losses = stats.get("losses", 0)
        user.draws = stats.get("draws", 0)
        user.games_played = stats.get("games_played", 0)
        
        user.last_login = data.get("last_login", time.time())
        user.is_logged_in = data.get("is_logged_in", False)
        
        return user


class UserManager:
    """Manages user accounts and authentication"""
    
    def __init__(self, users_file: str = "users.json"):
        self.users_file = users_file
        self.users: Dict[str, User] = {}  # user_id -> User
        self.usernames: Dict[str, str] = {}  # username -> user_id
        self.passwords: Dict[str, str] = {}  # user_id -> hashed_password
        
        # Load existing users if file exists
        self.load_users()
    
    def hash_password(self, password: str) -> str:
        """Hash a password for secure storage"""
        # Use SHA-256 for simplicity, in a real system use a more secure method
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register_user(self, username: str, password: str) -> Tuple[bool, Optional[User], str]:
        """
        Register a new user
        
        Args:
            username: Username for the new user
            password: Password for the new user
            
        Returns:
            Tuple containing:
            - Success flag
            - User object if successful, None otherwise
            - Error message if unsuccessful
        """
        # Check if username already exists
        if username in self.usernames:
            return False, None, "Username already exists"
        
        # Create new user
        user = User(username)
        hashed_password = self.hash_password(password)
        
        # Store user
        self.users[user.id] = user
        self.usernames[username] = user.id
        self.passwords[user.id] = hashed_password
        
        # Save to disk
        self.save_users()
        
        return True, user, ""
    
    def login_user(self, username: str, password: str) -> Tuple[bool, Optional[User], str]:
        """
        Log in a user
        
        Args:
            username: Username of the user
            password: Password of the user
            
        Returns:
            Tuple containing:
            - Success flag
            - User object if successful, None otherwise
            - Error message if unsuccessful
        """
        # Check if username exists
        if username not in self.usernames:
            return False, None, "Username not found"
        
        user_id = self.usernames[username]
        user = self.users[user_id]
        
        # Check password
        hashed_password = self.hash_password(password)
        if self.passwords[user_id] != hashed_password:
            return False, None, "Incorrect password"
        
        # Mark user as logged in
        user.login()
        self.save_users()
        
        return True, user, ""
    
    def logout_user(self, user_id: str) -> Tuple[bool, str]:
        """
        Log out a user
        
        Args:
            user_id: ID of the user to log out
            
        Returns:
            Tuple containing:
            - Success flag
            - Error message if unsuccessful
        """
        # Check if user exists
        if user_id not in self.users:
            return False, "User not found"
        
        # Mark user as logged out
        self.users[user_id].logout()
        self.save_users()
        
        return True, ""
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID"""
        return self.users.get(user_id)
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username"""
        if username in self.usernames:
            user_id = self.usernames[username]
            return self.users.get(user_id)
        return None
    
    def update_user_stats(self, user_id: str, win: bool = False, loss: bool = False, draw: bool = False) -> bool:
        """
        Update user statistics
        
        Args:
            user_id: ID of the user
            win: Whether to add a win
            loss: Whether to add a loss
            draw: Whether to add a draw
            
        Returns:
            Success flag
        """
        if user_id not in self.users:
            return False
        
        user = self.users[user_id]
        
        if win:
            user.add_win()
        elif loss:
            user.add_loss()
        elif draw:
            user.add_draw()
        
        self.save_users()
        return True
    
    def load_users(self):
        """Load users from disk"""
        if not os.path.exists(self.users_file):
            return
        
        try:
            with open(self.users_file, 'r') as f:
                data = json.load(f)
                
                # Load users
                for user_data in data.get("users", []):
                    user = User.from_dict(user_data)
                    self.users[user.id] = user
                    self.usernames[user.username] = user.id
                
                # Load passwords
                self.passwords = data.get("passwords", {})
                
        except Exception as e:
            print(f"Error loading users: {e}")
    
    def save_users(self):
        """Save users to disk"""
        try:
            data = {
                "users": [user.to_dict() for user in self.users.values()],
                "passwords": self.passwords
            }
            
            with open(self.users_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"Error saving users: {e}")
    
    def get_all_users(self) -> List[User]:
        """Get all registered users"""
        return list(self.users.values())