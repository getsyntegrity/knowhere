#!/usr/bin/env python3
"""
Log-management utility.

Use this helper to inspect, clean, and compress production, debug, and error logs.
"""

import argparse
from pathlib import Path
from datetime import datetime, timedelta
import gzip
import shutil


class LogManager:
    """Manage repo-local log files."""
    
    def __init__(self, logs_dir="logs"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(exist_ok=True)
    
    def list_logs(self, log_type=None):
        """List matching log files."""
        log_files = []
        
        for log_file in self.logs_dir.glob("*.log*"):
            if log_type:
                if log_type in log_file.name:
                    log_files.append(log_file)
            else:
                log_files.append(log_file)
        
        # Sort by modification time, newest first.
        log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        return log_files
    
    def show_logs(self, log_type=None, lines=50):
        """Show the tail of the newest matching log file."""
        log_files = self.list_logs(log_type)
        
        if not log_files:
            print(f"No {'matching ' if log_type else ''}log files found")
            return
        
        print(f"Found {len(log_files)} log files:")
        for i, log_file in enumerate(log_files):
            size = log_file.stat().st_size
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            print(f"{i+1:2d}. {log_file.name} ({size:,} bytes, {mtime.strftime('%Y-%m-%d %H:%M:%S')})")
        
        if log_files:
            latest_file = log_files[0]
            print(f"\nShowing the newest log file: {latest_file.name}")
            print("-" * 80)
            
            try:
                if latest_file.name.endswith('.gz'):
                    with gzip.open(latest_file, 'rt', encoding='utf-8') as f:
                        content = f.readlines()
                else:
                    with open(latest_file, 'r', encoding='utf-8') as f:
                        content = f.readlines()
                
                # Print the last N lines.
                for line in content[-lines:]:
                    print(line.rstrip())
                    
            except Exception as e:
                print(f"Failed to read the log file: {e}")
    
    def clean_old_logs(self, days=7, dry_run=True):
        """Delete log files older than the retention window."""
        cutoff_date = datetime.now() - timedelta(days=days)
        cleaned_files = []
        
        for log_file in self.logs_dir.glob("*.log*"):
            file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
            if file_time < cutoff_date:
                cleaned_files.append(log_file)
                if not dry_run:
                    log_file.unlink()
        
        if cleaned_files:
            print(f"Found {len(cleaned_files)} log files older than {days} days:")
            for log_file in cleaned_files:
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                print(f"  - {log_file.name} ({file_time.strftime('%Y-%m-%d %H:%M:%S')})")
            
            if not dry_run:
                print("Deleted the files above")
            else:
                print("(Preview mode. Use --execute to delete files.)")
        else:
            print(f"No log files older than {days} days were found")
    
    def compress_logs(self, days=1):
        """Compress log files older than the retention window."""
        cutoff_date = datetime.now() - timedelta(days=days)
        compressed_files = []
        
        for log_file in self.logs_dir.glob("*.log"):
            if not log_file.name.endswith('.gz'):
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_time < cutoff_date:
                    compressed_file = log_file.with_suffix('.log.gz')
                    try:
                        with open(log_file, 'rb') as f_in:
                            with gzip.open(compressed_file, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        log_file.unlink()
                        compressed_files.append(compressed_file)
                    except Exception as e:
                        print(f"Failed to compress {log_file.name}: {e}")
        
        if compressed_files:
            print(f"Compressed {len(compressed_files)} log files:")
            for compressed_file in compressed_files:
                print(f"  - {compressed_file.name}")
        else:
            print("No log files needed compression")
    
    def get_log_stats(self):
        """Return log-file statistics grouped by type."""
        stats = {
            'production': {'files': 0, 'size': 0},
            'debug': {'files': 0, 'size': 0},
            'error': {'files': 0, 'size': 0},
            'total': {'files': 0, 'size': 0}
        }
        
        for log_file in self.logs_dir.glob("*.log*"):
            size = log_file.stat().st_size
            stats['total']['files'] += 1
            stats['total']['size'] += size
            
            if 'production' in log_file.name:
                stats['production']['files'] += 1
                stats['production']['size'] += size
            elif 'debug' in log_file.name:
                stats['debug']['files'] += 1
                stats['debug']['size'] += size
            elif 'error' in log_file.name:
                stats['error']['files'] += 1
                stats['error']['size'] += size
        
        return stats


def format_size(size_bytes):
    """Render a byte count with a human-readable unit."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def main():
    parser = argparse.ArgumentParser(description="Log-management utility")
    parser.add_argument("--logs-dir", default="logs", help="Path to the log directory")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # List log files.
    list_parser = subparsers.add_parser("list", help="List log files")
    list_parser.add_argument("--type", choices=["production", "debug", "error"], help="Log type")
    
    # Show log content.
    show_parser = subparsers.add_parser("show", help="Show log content")
    show_parser.add_argument("--type", choices=["production", "debug", "error"], help="Log type")
    show_parser.add_argument("--lines", type=int, default=50, help="Number of lines to show")
    
    # Clean old logs.
    clean_parser = subparsers.add_parser("clean", help="Delete old log files")
    clean_parser.add_argument("--days", type=int, default=7, help="Retention period in days")
    clean_parser.add_argument("--execute", action="store_true", help="Delete files instead of previewing")
    
    # Compress logs.
    compress_parser = subparsers.add_parser("compress", help="Compress old log files")
    compress_parser.add_argument("--days", type=int, default=1, help="Compress files older than this many days")
    
    # Show statistics.
    stats_parser = subparsers.add_parser("stats", help="Show log statistics")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    log_manager = LogManager(args.logs_dir)
    
    if args.command == "list":
        log_files = log_manager.list_logs(args.type)
        if log_files:
            print(f"Log files ({args.type or 'all'}):")
            for log_file in log_files:
                size = log_file.stat().st_size
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                print(f"  {log_file.name} ({format_size(size)}, {mtime.strftime('%Y-%m-%d %H:%M:%S')})")
        else:
            print("No log files found")
    
    elif args.command == "show":
        log_manager.show_logs(args.type, args.lines)
    
    elif args.command == "clean":
        log_manager.clean_old_logs(args.days, not args.execute)
    
    elif args.command == "compress":
        log_manager.compress_logs(args.days)
    
    elif args.command == "stats":
        stats = log_manager.get_log_stats()
        print("Log statistics:")
        print(f"  Production logs: {stats['production']['files']} files, {format_size(stats['production']['size'])}")
        print(f"  Debug logs: {stats['debug']['files']} files, {format_size(stats['debug']['size'])}")
        print(f"  Error logs: {stats['error']['files']} files, {format_size(stats['error']['size'])}")
        print(f"  Total: {stats['total']['files']} files, {format_size(stats['total']['size'])}")


if __name__ == "__main__":
    main()
