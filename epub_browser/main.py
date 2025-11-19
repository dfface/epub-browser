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
import argparse
from tqdm import tqdm
from watchdog.observers import Observer

from .server import EPUBServer
from .library import EPUBLibrary
from .watch import EPUBWatcher

def start_watcher_process(filenames, library, stop_event):
    """启动文件监控进程"""
    try:
        watcher = EPUBWatcher(filenames, library)
        watcher.watch(stop_event)
    except Exception as e:
        print(f"Watcher process error: {e}")

def start_server_process(base_dir, book_count, port, no_browser, log_enabled, stop_event):
    """启动服务器进程"""
    try:
        server_instance = EPUBServer(base_dir, book_count, log_enabled)
        server_instance.start_server(
            port=port, 
            no_browser=no_browser,
            stop_event=stop_event
        )
    except Exception as e:
        print(f"Server process error: {e}")

def main():
    parser = argparse.ArgumentParser(description='EPUB to Web Converter - Multi-book Support')
    parser.add_argument('filename', nargs='+', help='EPUB file path(s)')
    parser.add_argument('--port', '-p', type=int, default=8000, help='Web server port (default: 8000)')
    parser.add_argument('--no-browser', action='store_true', help='Do not automatically open browser')
    parser.add_argument('--output-dir', '-o', help='Output directory for converted books')
    parser.add_argument('--keep-files', action='store_true', help='Keep converted files after server stops. To enable direct deployment, please use the --no-server parameter.')
    parser.add_argument('--log', action='store_true', help='Enable log messages')
    parser.add_argument('--no-server', action='store_true', help='Do not start a server, just generate files which can be directly deployed on any web server such as Apache.')
    parser.add_argument('--watch', '-w', action='store_true', help="Monitor all EPUB files in the directory specified by the user (or the directory where the EPUB file resides). When there are new additions or updates, automatically add them to the library.")
    
    args = parser.parse_args()
    
    # 检查文件是否存在
    for filename in args.filename:
        if not os.path.exists(filename):
            print(f"Error: File '{filename}' does not exist")
            sys.exit(1)
    
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

    if success_count == 0:
        print("No books were successfully processed")
        sys.exit(1)
    
    # 创建 library home
    library.create_library_home()
    # 添加静态资源
    library.add_assets()
    # 重新组织文件位置
    library.reorganize_files()

    # 仅生成文件
    if args.no_server:
        print(f"Files generated in: {library.base_directory}")
        return

    # 创建进程停止事件
    stop_event = multiprocessing.Event()

    # 信号处理函数
    def signal_handler(sig, frame):
        print("\nShutting down...")
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
        args=(library.base_directory, len(library.books), args.port, args.no_browser, args.log, stop_event),
        name="ServerProcess"
    )
    server_process.daemon = True
    server_process.start()

    # 启动监控进程（如果需要）
    watcher_process = None
    if args.watch:
        watcher_process = multiprocessing.Process(
            target=start_watcher_process,
            args=(args.filename, library, stop_event),
            name="WatcherProcess"
        )
        watcher_process.daemon = True
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
                print("All processes have terminated")
                break
                
            # 检查停止事件
            if stop_event.is_set():
                break
                
            # 短暂休眠避免过度占用CPU
            import time
            time.sleep(0.1)
                
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop_event.set()
    except Exception as e:
        print(f"Error occurred: {e}")
        stop_event.set()
    finally:
        # 等待进程结束
        for process in processes:
            if process.is_alive():
                process.join(timeout=5)
                if process.is_alive():
                    print(f"Force terminating {process.name}")
                    process.terminate()


if __name__ == '__main__':
    # 确保在Windows上正确运行多进程
    if sys.platform.startswith('win'):
        multiprocessing.freeze_support()
    main()