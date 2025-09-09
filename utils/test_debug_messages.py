"""
測試所有調試信息是否正確顯示
執行此腳本以確認調試系統工作正常
"""
import os
import sys
import time

# 確保能夠導入模組
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # 獲取父目錄（項目根目錄）
sys.path.insert(0, parent_dir)  # 將項目根目錄加入路徑

print(f"項目根目錄: {parent_dir}")
print(f"腳本目錄: {current_dir}")

# 確保 psutil 已安裝
try:
    import psutil
    print("✓ psutil 已安裝")
except ImportError:
    print("❌ psutil 未安裝，請執行 'pip install psutil'")
    print("某些監控功能將無法使用")

# 載入配置
try:
    import config.settings as settings
    print(f"✓ 設定已載入")
    print(f"  - SHOW_DEBUG_MESSAGES: {getattr(settings, 'SHOW_DEBUG_MESSAGES', '未設定')}")
    print(f"  - ENABLE_MEMORY_MONITOR: {getattr(settings, 'ENABLE_MEMORY_MONITOR', '未設定')}")
    print(f"  - LOG_FOLDER: {getattr(settings, 'LOG_FOLDER', '未設定')}")
except Exception as e:
    print(f"❌ 無法載入設定: {e}")

# 啟用增強日誌系統
try:
    from enhanced_logging_and_error_handler import (
        configure, 
        setup_global_error_handler, 
        log_operation, 
        log_memory_usage,
        log_open_files,
        toggle_detailed_logging
    )
    
    # 強制開啟詳細日誌
    configure(settings)
    toggle_detailed_logging(True)
    setup_global_error_handler()
    print("✓ 增強日誌系統已載入")
except ImportError as e:
    print(f"❌ 增強日誌系統未找到: {e}")
    sys.exit(1)

# 測試基本日誌功能
print("\n=== 測試基本日誌功能 ===")
log_operation("測試操作", {"測試項目": "基本日誌"})
mem = log_memory_usage("測試記憶體監控")
files = log_open_files()
print(f"當前記憶體使用: {mem:.2f} MB")
print(f"打開的檔案數量: {files or '無法取得'}")

# 測試檔案信息記錄
print("\n=== 測試檔案信息記錄 ===")
test_file = os.path.join(current_dir, "test_debug_messages.py")
file_size = os.path.getsize(test_file) / (1024 * 1024)
modified_time = os.path.getmtime(test_file)
access_time = os.path.getatime(test_file)

from datetime import datetime
print(f"[file-info] 大小: {file_size:.2f} MB")
print(f"[file-info] 修改時間: {datetime.fromtimestamp(modified_time)}")
print(f"[file-info] 存取時間: {datetime.fromtimestamp(access_time)}")
print(f"[file-info] 存取間隔: {access_time - modified_time:.2f} 秒")

# 測試垃圾回收記錄
print("\n=== 測試垃圾回收記錄 ===")
import gc
# 創建一些垃圾對象
garbage = [list(range(100)) for _ in range(1000)]
counts_before = gc.get_count()
print(f"[gc] 回收前對象: {counts_before}")
# 解釋垃圾回收計數
print(f"  - 第0代 (新對象): {counts_before[0]} 個")
print(f"  - 第1代 (中年對象): {counts_before[1]} 個")
print(f"  - 第2代 (老對象): {counts_before[2]} 個")
# 執行垃圾回收
collected = gc.collect(2)
counts_after = gc.get_count()
print(f"[gc] 回收後對象: {counts_after}, 釋放: {collected}")

# 測試警告信息
print("\n=== 測試警告信息 ===")
print(f"[warning] 記憶體增長過大: +126.45 MB (示範)")
print(f"[warning] 打開檔案數過多: 78 (示範)")

# 測試錯誤處理器
print("\n=== 測試錯誤處理器 ===")
print("將觸發一個除零錯誤作為測試...")
print("檢查 error_logs 資料夾中是否生成了崩潰報告")
print("準備在 5 秒後觸發錯誤...")

for i in range(5, 0, -1):
    print(f"{i}...")
    time.sleep(1)

try:
    result = 1 / 0  # 將觸發除零錯誤
except ZeroDivisionError:
    print("✓ 錯誤已捕捉，檢查是否生成了錯誤報告")
    error_log_dir = os.path.join(getattr(settings, 'LOG_FOLDER', current_dir), "error_logs")
    if os.path.exists(error_log_dir):
        files = os.listdir(error_log_dir)
        crash_files = [f for f in files if f.startswith("crash_")]
        if crash_files:
            print(f"✓ 找到 {len(crash_files)} 個崩潰報告:")
            for f in crash_files[-3:]:  # 只顯示最新的3個
                print(f"  - {f}")
        else:
            print("❌ 沒有找到崩潰報告")
    else:
        print(f"❌ 錯誤日誌目錄不存在: {error_log_dir}")

print("\n測試完成！")