import json
import os
from datetime import datetime

class HistoryManager:
    def __init__(self, history_file='history.json', max_entries=50):
        self.history_file = history_file
        self.max_entries = max_entries
        self.history = self.load_history()
    
    def load_history(self):
        """Load history from JSON file"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []
    
    def save_history(self):
        """Save history to JSON file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except IOError:
            pass
    
    def add_entry(self, repo_path, output_path, mode, parameters, archive_format='zip', status='success'):
        """Add a new entry to history"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'repo_path': repo_path,
            'output_path': output_path,
            'mode': mode,
            'parameters': parameters,
            'archive_format': archive_format,
            'status': status
        }
        self.history.insert(0, entry)  # Add to beginning
        
        # Keep only max_entries
        if len(self.history) > self.max_entries:
            self.history = self.history[:self.max_entries]
        
        self.save_history()
    
    def get_history(self):
        """Get all history entries"""
        return self.history
    
    def clear_history(self):
        """Clear all history"""
        self.history = []
        self.save_history()
    
    def get_entry(self, index):
        """Get a specific history entry by index"""
        if 0 <= index < len(self.history):
            return self.history[index]
        return None

