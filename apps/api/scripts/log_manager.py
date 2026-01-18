#!/usr/bin/env python3
"""
日志管理脚本
用于管理分离的日志文件：生产日志、调试日志、错误日志
"""

import argparse
from pathlib import Path
from datetime import datetime, timedelta
import gzip
import shutil


class LogManager:
    """日志管理器"""
    
    def __init__(self, logs_dir="logs"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(exist_ok=True)
    
    def list_logs(self, log_type=None):
        """列出日志文件"""
        log_files = []
        
        for log_file in self.logs_dir.glob("*.log*"):
            if log_type:
                if log_type in log_file.name:
                    log_files.append(log_file)
            else:
                log_files.append(log_file)
        
        # 按修改时间排序
        log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        return log_files
    
    def show_logs(self, log_type=None, lines=50):
        """显示日志内容"""
        log_files = self.list_logs(log_type)
        
        if not log_files:
            print(f"未找到{'指定类型' if log_type else ''}的日志文件")
            return
        
        print(f"找到 {len(log_files)} 个日志文件:")
        for i, log_file in enumerate(log_files):
            size = log_file.stat().st_size
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            print(f"{i+1:2d}. {log_file.name} ({size:,} bytes, {mtime.strftime('%Y-%m-%d %H:%M:%S')})")
        
        if log_files:
            latest_file = log_files[0]
            print(f"\n显示最新日志文件: {latest_file.name}")
            print("-" * 80)
            
            try:
                if latest_file.name.endswith('.gz'):
                    with gzip.open(latest_file, 'rt', encoding='utf-8') as f:
                        content = f.readlines()
                else:
                    with open(latest_file, 'r', encoding='utf-8') as f:
                        content = f.readlines()
                
                # 显示最后N行
                for line in content[-lines:]:
                    print(line.rstrip())
                    
            except Exception as e:
                print(f"读取日志文件失败: {e}")
    
    def clean_old_logs(self, days=7, dry_run=True):
        """清理旧日志文件"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cleaned_files = []
        
        for log_file in self.logs_dir.glob("*.log*"):
            file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
            if file_time < cutoff_date:
                cleaned_files.append(log_file)
                if not dry_run:
                    log_file.unlink()
        
        if cleaned_files:
            print(f"找到 {len(cleaned_files)} 个超过 {days} 天的日志文件:")
            for log_file in cleaned_files:
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                print(f"  - {log_file.name} ({file_time.strftime('%Y-%m-%d %H:%M:%S')})")
            
            if not dry_run:
                print("已删除上述文件")
            else:
                print("(预览模式，使用 --execute 参数实际删除)")
        else:
            print(f"没有找到超过 {days} 天的日志文件")
    
    def compress_logs(self, days=1):
        """压缩旧日志文件"""
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
                        print(f"压缩 {log_file.name} 失败: {e}")
        
        if compressed_files:
            print(f"已压缩 {len(compressed_files)} 个日志文件:")
            for compressed_file in compressed_files:
                print(f"  - {compressed_file.name}")
        else:
            print(f"没有找到需要压缩的日志文件")
    
    def get_log_stats(self):
        """获取日志统计信息"""
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
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def main():
    parser = argparse.ArgumentParser(description="日志管理工具")
    parser.add_argument("--logs-dir", default="logs", help="日志目录路径")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 列出日志文件
    list_parser = subparsers.add_parser("list", help="列出日志文件")
    list_parser.add_argument("--type", choices=["production", "debug", "error"], help="日志类型")
    
    # 显示日志内容
    show_parser = subparsers.add_parser("show", help="显示日志内容")
    show_parser.add_argument("--type", choices=["production", "debug", "error"], help="日志类型")
    show_parser.add_argument("--lines", type=int, default=50, help="显示行数")
    
    # 清理旧日志
    clean_parser = subparsers.add_parser("clean", help="清理旧日志文件")
    clean_parser.add_argument("--days", type=int, default=7, help="保留天数")
    clean_parser.add_argument("--execute", action="store_true", help="实际执行删除")
    
    # 压缩日志
    compress_parser = subparsers.add_parser("compress", help="压缩旧日志文件")
    compress_parser.add_argument("--days", type=int, default=1, help="压缩多少天前的日志")
    
    # 统计信息
    stats_parser = subparsers.add_parser("stats", help="显示日志统计信息")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    log_manager = LogManager(args.logs_dir)
    
    if args.command == "list":
        log_files = log_manager.list_logs(args.type)
        if log_files:
            print(f"日志文件 ({args.type or '全部'}):")
            for log_file in log_files:
                size = log_file.stat().st_size
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                print(f"  {log_file.name} ({format_size(size)}, {mtime.strftime('%Y-%m-%d %H:%M:%S')})")
        else:
            print("未找到日志文件")
    
    elif args.command == "show":
        log_manager.show_logs(args.type, args.lines)
    
    elif args.command == "clean":
        log_manager.clean_old_logs(args.days, not args.execute)
    
    elif args.command == "compress":
        log_manager.compress_logs(args.days)
    
    elif args.command == "stats":
        stats = log_manager.get_log_stats()
        print("日志统计信息:")
        print(f"  生产日志: {stats['production']['files']} 个文件, {format_size(stats['production']['size'])}")
        print(f"  调试日志: {stats['debug']['files']} 个文件, {format_size(stats['debug']['size'])}")
        print(f"  错误日志: {stats['error']['files']} 个文件, {format_size(stats['error']['size'])}")
        print(f"  总计: {stats['total']['files']} 个文件, {format_size(stats['total']['size'])}")


if __name__ == "__main__":
    main()
