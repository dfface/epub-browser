#!/usr/bin/env python3
"""
EPUB to Web Converter
将EPUB文件转换为可在浏览器中阅读的网页格式
支持多本书籍同时转换
"""

import os
import sys
import threading
import multiprocessing
import signal
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from tqdm import tqdm
from watchdog.observers import Observer

from .cli import SSGConfig, ServerConfig, format_legacy_migration_hint, parse_cli
from .server import EPUBServer
from .library import EPUBLibrary
from .reporting import Reporter
from .runtime import run_server
from .ssg import run_ssg
from .watch import EPUBWatcher

def start_watcher_process(filenames, library, stop_event, log_enabled=False):
    """启动文件监控进程"""
    try:
        watcher = EPUBWatcher(filenames, library)
        watcher.watch(stop_event)
    except Exception as e:
        Reporter(log_enabled).error(f"Watcher process error: {e}")

def start_server_process(base_dir, book_count, port, no_browser, log_enabled, stop_event, sync_dir=None):
    """启动服务器进程"""
    try:
        server_instance = EPUBServer(base_dir, book_count, log_enabled, sync_dir)
        server_instance.start_server(
            port=port, 
            no_browser=no_browser,
            stop_event=stop_event
        )
    except Exception as e:
        Reporter(log_enabled).error(f"Server process error: {e}")

def _run_existing_pipeline(config, reporter):
    is_ssg = isinstance(config, SSGConfig)
    args = SimpleNamespace(
        filename=[str(path) for path in config.sources],
        port=8000 if is_ssg else config.port,
        no_browser=True if is_ssg else config.no_browser,
        output_dir=(str(config.output_dir) if is_ssg and config.output_dir else
                    str(config.server_dir) if not is_ssg and config.server_dir else None),
        keep_files=(True if is_ssg else bool(config.server_dir) or config.retain_legacy_temporary_dir),
        log=config.log,
        no_server=is_ssg,
        watch=False if is_ssg else config.watch,
        sync_dir=None if is_ssg else (
            str(config.legacy_sync_dir) if config.legacy_sync_dir else None
        ),
    )
    
    # 检查文件是否存在
    for filename in args.filename:
        if not os.path.exists(filename):
            reporter.error(f"Error: File '{filename}' does not exist")
            return 4 if is_ssg else 5
    
    # 创建图书馆
    library = EPUBLibrary(args.output_dir)

    # 收集所有的 epub file，可能传递了路径需要下钻
    real_epub_files = []
    for filename in args.filename:
        cur_files = library.epub_file_discover(filename)
        real_epub_files.extend(cur_files)

    # 添加所有书籍
    # 线程安全相关变量
    success_count = 0
    count_lock = threading.Lock()  # 保证计数器操作的原子性
    progress_lock = threading.Lock()  # 保证 tqdm 进度条显示正常

    # 创建进度条（总任务数为文件数量）
    reporter.progress_active = True
    pbar = tqdm(total=len(real_epub_files), desc="Processing books")

    # 多线程处理函数：添加单本书籍
    def add_book_thread(filename, pbar):
        nonlocal success_count
        # 调用 add_book 添加书籍（假设该方法线程安全，若不安全需额外加锁）
        result, book_info = library.add_book(filename)
        # 线程安全地更新计数器和进度条
        with count_lock:
            if result:
                success_count += 1
        with progress_lock:
            pbar.update(1)  # 每次处理完一本书，更新进度条

    # 创建并启动线程
    with ThreadPoolExecutor(max_workers=10) as executor:  # 限制最大10个并发线程
        futures = []
        for filename in real_epub_files:
            # 使用线程池提交任务
            future = executor.submit(add_book_thread, filename, pbar)
            futures.append(future)
    
    # 关闭进度条
    pbar.close()
    reporter.progress_active = False

    if success_count == 0:
        reporter.error("No books were successfully processed")
        return 4 if is_ssg else 5
    
    # 创建 library home
    library.create_library_home()
    # 添加静态资源
    library.add_assets()
    # 重新组织文件位置
    library.reorganize_files()

    # 仅生成文件
    if args.no_server:
        reporter.result(f"Files generated in: {library.base_directory}")
        return 0

    # 创建进程停止事件
    stop_event = multiprocessing.Event()

    # 信号处理函数
    def signal_handler(sig, frame):
        reporter.notice("Shutting down...")
        stop_event.set()
        # 等待进程结束
        if 'server_process' in locals() and server_process.is_alive():
            server_process.join(timeout=5)
        if args.watch and 'watcher_process' in locals() and watcher_process.is_alive():
            watcher_process.join(timeout=5)
        
        if not args.keep_files:
            library.cleanup()
        sys.exit(0)

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动服务器进程
    server_process = multiprocessing.Process(
        target=start_server_process,
        args=(library.base_directory, len(library.books), args.port, args.no_browser, args.log, stop_event, args.sync_dir),
        name="ServerProcess"
    )
    server_process.start()

    # 启动监控进程（如果需要）
    watcher_process = None
    if args.watch:
        watcher_process = multiprocessing.Process(
            target=start_watcher_process,
            args=(args.filename, library, stop_event, args.log),
            name="WatcherProcess"
        )
        watcher_process.start()

    try:
        # 主进程等待子进程
        processes = [server_process]
        if watcher_process:
            processes.append(watcher_process)

        while True:
            # 检查进程是否存活
            alive_processes = [p for p in processes if p.is_alive()]
            if not alive_processes:
                reporter.detail("All processes have terminated")
                break
                
            # 检查停止事件
            if stop_event.is_set():
                break
                
            # 短暂休眠避免过度占用CPU
            import time
            time.sleep(0.1)
                
    except KeyboardInterrupt:
        reporter.notice("Shutting down...")
        stop_event.set()
    except Exception as e:
        reporter.error(f"Error occurred: {e}")
        stop_event.set()
    finally:
        # 等待进程结束
        sys.stdout.flush()
        sys.stderr.flush()
        for process in processes:
            if process.is_alive():
                process.join(timeout=5)
                if process.is_alive():
                    reporter.detail(f"Force terminating {process.name}")
                    process.terminate()
    return 0


def main(argv=None):
    config = parse_cli(sys.argv[1:] if argv is None else argv)
    reporter = Reporter(config.log)
    hint = format_legacy_migration_hint(config)
    if hint:
        reporter.notice(hint)
    if isinstance(config, SSGConfig):
        return run_ssg(config, reporter)
    return run_server(config, reporter)


if __name__ == '__main__':
    # 确保在Windows上正确运行多进程
    if sys.platform.startswith('win'):
        multiprocessing.freeze_support()
    raise SystemExit(main())
