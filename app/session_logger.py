"""
Gestion du log CSV de session.
"""
import csv
from datetime import datetime
from pathlib import Path


CSV_HEADERS = [
    'SN', 'MTM', 'BIOS_version',
    'Date', 'Heure_debut', 'Heure_fin', 'Duree_min',
    'Stock_MD5', 'Patched_MD5',
    'Chip_model', 'Chip_size_kB',
    'Verify_patched', 'Verify_restore',
    'Statut', 'Notes',
]


class SessionLogger:
    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_csv()
        self.entries = []
    
    def _init_csv(self):
        if not self.csv_path.exists():
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(CSV_HEADERS)
    
    def add_entry(self, **kwargs):
        row = {h: kwargs.get(h, '') for h in CSV_HEADERS}
        self.entries.append(row)
        with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
            csv.DictWriter(f, fieldnames=CSV_HEADERS).writerow(row)
    
    def session_summary(self) -> dict:
        total = len(self.entries)
        success = sum(1 for e in self.entries if e['Statut'] == 'SUCCESS')
        return {
            'total': total,
            'success': success,
            'failed': total - success,
            'csv_path': str(self.csv_path),
        }


def make_session_csv_path(reports_dir: str = './reports') -> str:
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    return str(Path(reports_dir) / f'session_{timestamp}.csv')
