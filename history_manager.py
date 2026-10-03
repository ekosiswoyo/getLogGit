import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from app_storage import data_directory, legacy_paths


class HistoryManager:
    def __init__(self, history_file=None, max_entries=50):
        self.history_file = Path(history_file) if history_file is not None else data_directory() / 'history.json'
        self.max_entries = max_entries
        self.history = self.load_history()
        if history_file is None and not self.history_file.exists():
            for legacy in legacy_paths('history.json'):
                if legacy == self.history_file or not legacy.is_file():
                    continue
                entries = self._read(legacy)
                if entries:
                    self.history = entries[:max_entries]
                    self.save_history()
                    break

    @staticmethod
    def _read(path):
        try:
            with open(path, encoding='utf-8') as source:
                entries = json.load(source)
            return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []
        except (ValueError, OSError):
            return []

    def load_history(self):
        return self._read(self.history_file)

    def save_history(self):
        """Replace atomically; report write errors instead of silently losing data."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=self.history_file.parent, delete=False) as target:
                temporary = target.name
                json.dump(self.history, target, indent=2, ensure_ascii=False)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.history_file)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def add_entry(self, repo_path, output_path, mode, parameters, archive_format='zip', status='success'):
        entry = {
            'timestamp': datetime.now().isoformat(),
            'repo_path': repo_path,
            'output_path': output_path,
            'mode': mode,
            'parameters': dict(parameters),
            'archive_format': archive_format,
            'status': status,
        }
        self.history.insert(0, entry)
        self.history = self.history[:self.max_entries]
        self.save_history()

    def get_history(self):
        return self.history

    def clear_history(self):
        self.history = []
        self.save_history()

    def get_entry(self, index):
        if 0 <= index < len(self.history):
            return self.history[index]
        return None
