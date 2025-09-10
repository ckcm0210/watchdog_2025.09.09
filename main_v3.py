"""
Excel Monitor 主執行檔案
這是唯一需要執行的檔案
(版本：加入最少入侵性診斷/輸出補強 + thread list + thread dump + heartbeat)
如需回復原始行為：刪除「最少入侵性輸出與診斷補強區」整段即可。
"""

import os
os.environ['OPENPYXL_LXML'] = 'True'  # 嘗試減少 0x80000003 問題（視乎 openpyxl/lxml 情況）

import gc
# 你要求改成：
gc.set_threshold(500000, 100, 100)
# 註：數值越大代表 GC 執行次數越少→ 暫存物件堆積更久。若記憶體升得太快可再調整。

import sys
import signal
import threading
import time
from datetime import datetime
import logging
import faulthandler
import traceback
import datetime
import atexit

# ================== 最少入侵性輸出與診斷補強區（全部可開關/刪除） ==================
# 功能開關（需要就 True，不要就 False）
ENABLE_STDOUT_LINE_BUFFERING = True           # 嘗試逐行 flush（Python 3.7+）
ENABLE_AUTO_FLUSH_PRINT = True                # 為所有 print 自動加 flush=True
ENABLE_FIRST_SIGINT_THREAD_DUMP = True        # 首次 Ctrl+C 只輸出執行緒堆疊，不停程序
ENABLE_HEARTBEAT = True                       # 主 loop 心跳
HEARTBEAT_INTERVAL = 30                       # 心跳秒數
HEARTBEAT_SHOW_THREAD_COUNT = True            # 心跳顯示 thread 數量
HEARTBEAT_DUMP_ON_THREAD_CHANGE = False       # thread 數有變化時列出 thread 名單
_first_sigint_pending_dump = True             # 內部旗標，不要手動改

if ENABLE_STDOUT_LINE_BUFFERING:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

if ENABLE_AUTO_FLUSH_PRINT:
    import builtins as _b
    if not getattr(_b, "_ORIGINAL_PRINT_SAVED", False):
        _orig_print = _b.print
        def _auto_flush_print(*a, **kw):
            if 'flush' not in kw:
                kw['flush'] = True
            return _orig_print(*a, **kw)
        _b.print = _auto_flush_print
        _b._ORIGINAL_PRINT_SAVED = True

def _dump_threads(label="THREAD DUMP"):
    """輸出所有執行緒堆疊（重型診斷：用於卡住時）。"""
    try:
        print(f"\n==== {label} ====")
        frames = sys._current_frames()
        for th in threading.enumerate():
            print(f"\n-- Thread: {th.name} (id={th.ident}, daemon={th.daemon})")
            fr = frames.get(th.ident)
            if fr:
                for line in traceback.format_stack(fr):
                    print(line.rstrip())
        print("==== END DUMP ====\n")
    except Exception as e:
        print(f"[thread-dump-error] {e}")

def list_threads():
    """
    輕量列出目前所有 thread 名稱（不顯示 stack），觀察是否有 thread 泄漏。
    """
    try:
        print("=== THREADS ===")
        for t in threading.enumerate():
            print(f"{t.name} (daemon={t.daemon})")
        print("===============")
    except Exception as e:
        print(f"[list_threads-error] {e}")
# ================== 補強區結束 ==================


# 導入增強版錯誤處理與日誌系統
try:
    from utils.enhanced_logging_and_error_handler import setup_global_error_handler, configure, log_operation, log_memory_usage
    import config.settings as settings  # 先載入設定
    configure(settings)
    setup_global_error_handler()
    log_operation("程式啟動")
    log_memory_usage("啟動時")
except ImportError as e:
    print(f"注意: 無法導入增強日誌系統 ({e})，將使用標準錯誤處理")
except Exception as e:
    print(f"設置增強錯誤處理器時發生錯誤: {e}")

# 確保能夠導入模組（再次保險）
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 其他模組
import config.settings as settings  # 再保證一次
from utils.logging import init_logging
from utils.memory import check_memory_limit
from utils.helpers import get_all_excel_files, timeout_handler
from utils.compression import CompressionFormat, test_compression_support
from ui.console import init_console
from core.baseline import create_baseline_for_files_robust
from core.watcher import active_polling_handler, ExcelFileEventHandler
from core.comparison import set_current_event_number
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

# 全局控制台變數，用於清理
console = None


def signal_handler(signum, frame):
    """
    信號處理器，優雅地停止程序 / 首次 Ctrl+C 輸出診斷
    """
    global _first_sigint_pending_dump
    if ENABLE_FIRST_SIGINT_THREAD_DUMP and _first_sigint_pending_dump:
        _first_sigint_pending_dump = False
        print("\n(CTRL+C) 捕捉到 SIGINT，先輸出執行緒堆疊（再次 Ctrl+C 才進入停止流程）")
        _dump_threads()
        list_threads()
        return

    if not settings.force_stop:
        settings.force_stop = True
        print("\n🛑 收到中斷信號，正在安全停止...")
        if getattr(settings, 'current_processing_file', None):
            print(f"   目前處理檔案: {settings.current_processing_file}")
        active_polling_handler.stop()
        _cleanup_console()
        print("   (再按一次 Ctrl+C 強制退出)")
    else:
        print("\n💥 強制退出...")
        _cleanup_console()
        sys.exit(1)


def _cleanup_console():
    """清理控制台資源"""
    global console
    try:
        if console:
            console.stop()
            console = None
    except Exception:
        pass


def _cleanup_tkinter_vars():
    """安全 Tk 清理"""
    try:
        import gc
        gc.collect()
    except Exception:
        pass


atexit.register(_cleanup_console)
atexit.register(_cleanup_tkinter_vars)


def main():
    """
    主函數
    """
    global console

    # 初始化日誌系統
    init_logging()

    # 環境摘要
    try:
        py = sys.version.split()[0]
        exe = sys.executable
        ve = getattr(settings, 'VALUE_ENGINE', 'polars')
        csvp = getattr(settings, 'CSV_PERSIST', False)
        print(f"[env] python={py} | VALUE_ENGINE={ve} | CSV_PERSIST={csvp} | sys.executable={exe}")
        try:
            from utils.env_info import format_packages_versions_line, format_detected_packages_versions_line
            width = int(getattr(settings, 'DEBUG_WRAP_WIDTH', 0) or getattr(settings, 'CONSOLE_TERM_WIDTH_OVERRIDE', 120) or 120)
            for ln in format_packages_versions_line('[env]', width):
                print(ln)
            try:
                for ln in format_detected_packages_versions_line('[env]', width, workspace_root='.'):
                    print(ln)
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        pass

    print("Excel Monitor v2.1 啟動中...")

    # 測試壓縮支援
    test_compression_support()

    # 設定 UI
    try:
        from ui.settings_ui import show_settings_ui
        show_settings_ui()
        from config.runtime import load_runtime_settings
        if (load_runtime_settings() or {}).get('STARTUP_CANCELLED'):
            print('使用者取消啟動，退出程式。')
            return
    except Exception as e:
        print(f"設定 UI 啟動失敗，使用預設設定: {e}")

    # 初始化控制台
    console = init_console()

    # Timeline 伺服器
    try:
        if getattr(settings, 'ENABLE_TIMELINE_SERVER', True):
            def _run_timeline_server():
                try:
                    import git_viewer
                    host = getattr(settings, 'TIMELINE_SERVER_HOST', '127.0.0.1')
                    port = int(getattr(settings, 'TIMELINE_SERVER_PORT', 5000))
                    print(f"[timeline] 啟動於 http://{host}:{port}/ui/timeline")
                    git_viewer.app.run(host=host, port=port, debug=False, use_reloader=False)
                except Exception as e2:
                    print(f"[timeline] 啟動失敗: {e2}")
            t = threading.Thread(target=_run_timeline_server, daemon=True)
            t.start()
            try:
                if getattr(settings, 'OPEN_TIMELINE_ON_START', False):
                    import webbrowser
                    url = f"http://{getattr(settings, 'TIMELINE_SERVER_HOST', '127.0.0.1')}:{int(getattr(settings, 'TIMELINE_SERVER_PORT', 5000))}/ui/timeline"
                    webbrowser.open(url)
            except Exception:
                pass
    except Exception:
        pass

    # 設定信號處理
    signal.signal(signal.SIGINT, signal_handler)

    # 超時監控
    if getattr(settings, 'ENABLE_TIMEOUT', False):
        timeout_thread = threading.Thread(target=timeout_handler, daemon=True)
        timeout_thread.start()

    # 壓縮格式
    available_formats = CompressionFormat.get_available_formats()
    print(f"🗜️  支援壓縮格式: {', '.join(available_formats)}")
    validated_format = CompressionFormat.validate_format(settings.DEFAULT_COMPRESSION_FORMAT)
    if validated_format != settings.DEFAULT_COMPRESSION_FORMAT:
        print(f"⚠️  格式已調整: {settings.DEFAULT_COMPRESSION_FORMAT} → {validated_format}")
        settings.DEFAULT_COMPRESSION_FORMAT = validated_format

    print(f"📁 監控資料夾: {settings.WATCH_FOLDERS}")
    if getattr(settings, 'MONITOR_ONLY_FOLDERS', None):
        print(f"🛈  只監控變更的根目錄: {settings.MONITOR_ONLY_FOLDERS}")
    print(f"📊 支援格式: {settings.SUPPORTED_EXTS}")
    print(f"⚙️  設定檔案: 已載入")

    # 手動基準線
    manual_files = []
    if settings.MANUAL_BASELINE_TARGET:
        print(f"📋 手動基準線目標: {len(settings.MANUAL_BASELINE_TARGET)} 個")
        for target in settings.MANUAL_BASELINE_TARGET:
            if os.path.exists(target):
                manual_files.append(target)
                print(f"   ✅ {os.path.basename(target)}")
            else:
                print(f"   ❌ 檔案不存在: {target}")

    # 掃描
    all_files = []
    if settings.SCAN_ALL_MODE:
        print("\n🔍 掃描所有 Excel 檔案...")
        try:
            from config.runtime import load_runtime_settings
            _rt_after_ui = load_runtime_settings() or {}
        except Exception:
            _rt_after_ui = {}
        rt_list = [r for r in (_rt_after_ui.get('SCAN_TARGET_FOLDERS', []) or []) if r]
        st_list = [r for r in (getattr(settings, 'SCAN_TARGET_FOLDERS', []) or []) if r]
        if rt_list:
            scan_roots = list(dict.fromkeys(rt_list))
            source_reason = 'runtime.SCAN_TARGET_FOLDERS'
        elif st_list:
            scan_roots = list(dict.fromkeys(st_list))
            source_reason = 'settings.SCAN_TARGET_FOLDERS'
        else:
            scan_roots = list(dict.fromkeys(list(settings.WATCH_FOLDERS or [])))
            source_reason = 'WATCH_FOLDERS (fallback)'
        all_files = get_all_excel_files(scan_roots)
        print(f"找到 {len(all_files)} 個 Excel 檔案（掃描根目錄: {scan_roots} | 來源: {source_reason}）")

    total_files = list(set(all_files + manual_files))
    if total_files:
        print(f"\n📊 總共需要處理 {len(total_files)} 個檔案")
        create_baseline_for_files_robust(total_files)

    # Watchdog 監控
    print("\n👀 啟動檔案監控...")
    event_handler = ExcelFileEventHandler(active_polling_handler)

    watch_roots = list(dict.fromkeys(list(settings.WATCH_FOLDERS or []) +
                                     list(getattr(settings, 'MONITOR_ONLY_FOLDERS', []) or [])))
    if not watch_roots:
        print("   ⚠️  沒有任何監控根目錄（WATCH_FOLDERS 或 MONITOR_ONLY_FOLDERS 為空）")

    def _is_unc_or_drive_root(p: str) -> bool:
        try:
            if not p:
                return False
            q = os.path.abspath(p)
            if q.startswith('\\\\'):
                return True
            drive, tail = os.path.splitdrive(q)
            if drive and (tail in ('\\', '/')):
                return True
        except Exception:
            pass
        return False

    def _truthy_env(name: str) -> bool:
        v = os.environ.get(name)
        return str(v).strip().lower() in ('1', 'true', 'yes', 'on') if v is not None else False

    backend = getattr(settings, 'OBSERVER_BACKEND', 'auto')
    if _truthy_env('WATCHDOG_FORCE_POLLING'):
        backend = 'polling'
    elif _truthy_env('WATCHDOG_BACKEND'):
        backend = os.environ.get('WATCHDOG_BACKEND')

    chosen_backend = 'native'
    if str(backend).lower() == 'polling':
        chosen_backend = 'polling'
    elif str(backend).lower() == 'auto':
        if any(_is_unc_or_drive_root(r) for r in (watch_roots or [])):
            chosen_backend = 'polling'
        else:
            chosen_backend = 'native'
    else:
        chosen_backend = 'native'

    observer = None
    try:
        if chosen_backend == 'polling':
            observer = PollingObserver()
            print("   使用輪詢後端 PollingObserver（更穩定）。")
        else:
            observer = Observer()
            print("   使用原生後端 Observer。")
    except Exception as e:
        print(f"   後端建立失敗（{e}），回退到 PollingObserver。")
        observer = PollingObserver()

    for folder in watch_roots:
        if os.path.exists(folder):
            try:
                observer.schedule(event_handler, folder, recursive=True)
                print(f"   監控: {folder}")
            except Exception as se:
                print(f"   ⚠️  註冊監控失敗（{se}），回退到 PollingObserver 重新啟動。")
                try:
                    observer.stop()
                except Exception:
                    pass
                observer = PollingObserver()
                observer.schedule(event_handler, folder, recursive=True)
                chosen_backend = 'polling'
                print("   切換為 PollingObserver 後端。")
        else:
            print(f"   ⚠️  資料夾不存在: {folder}")

    observer.start()

    print("\n✅ Excel Monitor 已啟動完成！")
    print(f"   - Watchdog 後端: {chosen_backend}")
    print("🎯 功能狀態:")
    print(f"   - 公式模式: {'開啟' if settings.FORMULA_ONLY_MODE else '關閉'}")
    print(f"   - 白名單過濾: {'開啟' if settings.WHITELIST_USERS else '關閉'}")
    print(f"   - 本地緩存: {'開啟' if settings.USE_LOCAL_CACHE else '關閉'}")
    print(f"   - 黑色控制台: {'開啟' if settings.ENABLE_BLACK_CONSOLE else '關閉'}")
    print(f"   - 記憶體監控: {'開啟' if settings.ENABLE_MEMORY_MONITOR else '關閉'}")
    print(f"   - 壓縮格式: {settings.DEFAULT_COMPRESSION_FORMAT.upper()}")
    print(f"   - 歸檔模式: {'開啟' if settings.ENABLE_ARCHIVE_MODE else '關閉'}")
    print("\n按 Ctrl+C 停止監控...")

    try:
        last_hb = 0.0
        prev_thread_count = len(threading.enumerate())
        while not settings.force_stop:
            now = time.time()
            if ENABLE_HEARTBEAT and (now - last_hb >= HEARTBEAT_INTERVAL):
                try:
                    cur_threads = len(threading.enumerate())
                    if HEARTBEAT_SHOW_THREAD_COUNT:
                        print(f"[heartbeat] alive {time.strftime('%H:%M:%S')} threads={cur_threads}")
                    else:
                        print(f"[heartbeat] alive {time.strftime('%H:%M:%S')}")
                    if HEARTBEAT_DUMP_ON_THREAD_CHANGE and cur_threads != prev_thread_count:
                        print(f"[heartbeat] thread count changed {prev_thread_count} -> {cur_threads}, dumping thread list...")
                        list_threads()
                        prev_thread_count = cur_threads
                except Exception:
                    pass
                last_hb = now
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n🔄 正在停止監控...")
        observer.stop()
        observer.join()
        active_polling_handler.stop()
        try:
            from utils.task_queue import get_compare_queue
            q = get_compare_queue(lambda p, evt: False)  # no-op
            q.stop()
        except Exception:
            pass
        _cleanup_console()
        print("✅ 監控已停止")


if __name__ == "__main__":
    log_directory = r"C:\temp\python_logs"
    os.makedirs(log_directory, exist_ok=True)

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    error_log = os.path.join(log_directory, f"python_crash_{timestamp}.log")

    try:
        with open(error_log, 'w', encoding='utf-8') as log_file:
            log_file.write(f"程式啟動: {datetime.datetime.now()}\n")
            log_file.write(f"Python版本: {sys.version}\n")
            log_file.write(f"執行環境: {'Jupyter' if 'ipykernel' in sys.modules else 'Standard Python'}\n")
            log_file.write("=" * 50 + "\n\n")
            log_file.flush()

            faulthandler.enable(file=log_file, all_threads=True)

            print("faulthandler 已啟用")
            print(f"錯誤記錄檔案: {error_log}")

            main()

    except Exception as e:
        print(f"程式錯誤: {type(e).__name__}: {e}")
        traceback.print_exc()

        with open(error_log, 'a', encoding='utf-8') as f:
            f.write(f"\nPython 例外錯誤:\n")
            f.write(f"時間: {datetime.datetime.now()}\n")
            f.write(f"錯誤: {type(e).__name__}: {e}\n")
            traceback.print_exc(file=f)

        sys.exit(1)
