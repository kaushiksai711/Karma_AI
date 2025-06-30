import sqlite3
from datetime import datetime
from typing import Set, Optional
import os

class DatabaseManager:
    def __init__(self, db_path: str = '/data/karma_rewards.db'):
        """
        Initialize the database manager.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self):
        """Create and return a new database connection."""
        return sqlite3.connect(self.db_path)
    
    def _init_db(self):
        """Initialize the database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Create new table with updated schema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_rewards (
                    date TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    box_type TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (date, user_id)
                )
            ''')
            conn.commit()
    
    def add_rewarded_user(self, date: str, user_id: str, box_type: str) -> None:
        """
        Add a user to the rewarded users for a specific date.
        If user already has a reward for this date, it will be updated.
        
        Args:
            date: Date string in YYYY-MM-DD format
            user_id: User ID
            box_type: Type of the box awarded
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                    INSERT INTO user_rewards (date, user_id, box_type)
                    VALUES (?, ?, ?)
                ''', (date, str(user_id), box_type))
            conn.commit()
    
    def is_user_rewarded(self, date: str, user_id: str, box_type: str) -> bool:
        """
        Check if a user was already rewarded on a specific date for a specific box type.
        
        Args:
            date: Date string in YYYY-MM-DD format
            user_id: User ID
            box_type: Type of the box to check
            
        Returns:
            bool: True if user was already rewarded, False otherwise
        """
        reward = self.get_user_reward(date, user_id)
        return reward is not None and reward['box_type'] == box_type
        
    def get_user_reward(self, date: str, user_id: str) -> Optional[dict]:
        """
        Get the reward details for a user on a specific date.
        
        Args:
            date: Date string in YYYY-MM-DD format
            user_id: User ID
            
        Returns:
            dict: Reward details or None if no reward exists
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT box_type, timestamp FROM user_rewards 
                WHERE date = ? AND user_id = ?
                LIMIT 1
            ''', (date, str(user_id)))
            row = cursor.fetchone()
            if row:
                return {
                    'box_type': row[0],
                    'timestamp': row[1]
                }
            return None
    
    def get_rewarded_users(self, date: str, box_type: Optional[str] = None) -> Set[str]:
        """
        Get all users who were rewarded on a specific date.
        
        Args:
            date: Date string in YYYY-MM-DD format
            box_type: Optional box type to filter by
            
        Returns:
            Set of user IDs
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if box_type:
                cursor.execute('''
                    SELECT user_id FROM user_rewards 
                    WHERE date = ? AND box_type = ?
                ''', (date, box_type))
            else:
                cursor.execute('''
                    SELECT user_id FROM user_rewards 
                    WHERE date = ?
                ''', (date,))
            
            return {row[0] for row in cursor.fetchall()}
    
    def cleanup_old_entries(self, days_to_keep: int = 30) -> None:
        """
        Clean up old entries from the database.
        
        Args:
            days_to_keep: Number of days of history to keep
        """
        cutoff_date = datetime.now().strftime('%Y-%m-%d')
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM user_rewards 
                WHERE date < date(?, ?)
            ''', (cutoff_date, f'-{days_to_keep} days'))
            conn.commit()
    
    def close(self):
        """Close any open database connections."""
        # SQLite connections are closed when they go out of scope
        # This method is kept for API compatibility
        pass
