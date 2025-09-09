# 🔧 **代碼重構檢查清單 (Refactoring Checklist)**
**日期**: 2025-09-07  
**項目**: Excel Watchdog UI 設定界面重構

---

## ⚠️ **常見重構錯誤分析**

### **1. Import 依賴問題 (最常見)**
**錯誤類型**:
- 移動文件後忘記更新 import 路徑
- 循環導入 (A 導入 B，B 又導入 A)
- 相對導入路徑錯誤
- 忘記在新文件中導入必要的模組

**具體例子**:
```python
# 錯誤: 移動文件後沒更新路徑
from ui.settings_ui import PARAMS_SPEC  # 文件已移動到 ui/settings/config_definitions/

# 正確: 更新後的路徑
from ui.settings.config_definitions.monitoring_config import MONITORING_CONFIG
```

### **2. 類和方法引用問題**
**錯誤類型**:
- 移動方法後忘記加 `self.`
- 類變數變成實例變數時引用錯誤
- 靜態方法和實例方法混淆
- 父類方法調用錯誤

**具體例子**:
```python
# 錯誤: 移動到類中後忘記加 self
def create_widget():
    return ttk.Entry(parent)  # parent 未定義

# 正確: 加上 self
def create_widget(self):
    return ttk.Entry(self.parent)
```

### **3. 全局變數和常數問題**
**錯誤類型**:
- 全局變數移動後引用失效
- 常數定義位置改變
- 模組級變數變成類變數時引用錯誤

### **4. 文件路徑和資源問題**
**錯誤類型**:
- 相對路徑在新位置失效
- 配置文件路徑錯誤
- 資源文件找不到

### **5. 命名空間衝突**
**錯誤類型**:
- 同名類或函數在不同模組中
- 變數名遮蔽 (shadowing)
- 模組名衝突

---

## ✅ **重構前檢查清單 (Pre-Refactoring Checklist)**

### **📋 階段一: 規劃檢查**
- [ ] **依賴關係圖**: 畫出當前文件的所有依賴關係
- [ ] **Import 清單**: 列出所有 import 語句和被 import 的位置
- [ ] **全局變數清單**: 記錄所有全局變數和常數
- [ ] **外部引用清單**: 找出所有外部對此文件的引用
- [ ] **測試覆蓋**: 確認有測試可以驗證重構後功能正常

### **📋 階段二: 移動前檢查**
- [ ] **備份原始文件**: 創建完整備份
- [ ] **新文件夾結構**: 確認新的文件夾結構正確
- [ ] **命名規範**: 確認新文件名符合項目規範
- [ ] **__init__.py 文件**: 確保所有新文件夾都有 __init__.py

---

## ✅ **重構中檢查清單 (During Refactoring)**

### **📋 移動代碼時**
- [ ] **逐段移動**: 不要一次移動太多代碼
- [ ] **保持原始結構**: 先移動再優化，不要同時做兩件事
- [ ] **註釋標記**: 在原位置留下註釋說明代碼移動到哪裡
- [ ] **版本控制**: 每個小步驟都提交到版本控制

### **📋 更新 Import 時**
- [ ] **相對路徑檢查**: 確認相對導入路徑正確
- [ ] **絕對路徑檢查**: 確認絕對導入路徑正確
- [ ] **循環導入檢查**: 檢查是否會造成循環導入
- [ ] **未使用導入清理**: 移除不再需要的 import

### **📋 修改類和方法時**
- [ ] **self 參數**: 確認所有實例方法都有 self 參數
- [ ] **self 引用**: 確認所有實例變數都用 self.variable
- [ ] **類變數引用**: 確認類變數用 ClassName.variable 或 cls.variable
- [ ] **方法調用**: 確認方法調用使用正確的語法

---

## ✅ **重構後檢查清單 (Post-Refactoring Checklist)**

### **📋 語法檢查**
- [ ] **Python 語法**: 使用 `python -m py_compile file.py` 檢查語法
- [ ] **Import 測試**: 嘗試導入所有新模組
- [ ] **循環導入檢查**: 運行 `python -c "import module_name"` 檢查每個模組

### **📋 功能測試**
- [ ] **基本啟動**: 程序能正常啟動
- [ ] **核心功能**: 主要功能正常工作
- [ ] **UI 測試**: 所有界面元素正常顯示和響應
- [ ] **錯誤處理**: 錯誤處理機制仍然有效

### **📋 性能檢查**
- [ ] **記憶體使用**: 檢查記憶體使用是否符合預期
- [ ] **載入時間**: 測量載入時間是否改善
- [ ] **響應速度**: 檢查響應速度是否正常

---

## 🔍 **具體檢查命令**

### **語法檢查命令**
```bash
# 檢查單個文件語法
python -m py_compile ui/settings/config_definitions/monitoring_config.py

# 檢查整個目錄
python -m compileall ui/settings/

# 檢查導入
python -c "from ui.settings.config_definitions import monitoring_config; print('Import OK')"
```

### **快速功能測試**
```python
# 創建簡單測試腳本
def quick_test():
    try:
        # 測試導入
        from ui.settings_ui import SettingsDialog
        print("✅ Import 成功")
        
        # 測試基本初始化
        # (不實際顯示 UI)
        print("✅ 基本功能正常")
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return False
    return True

if __name__ == "__main__":
    quick_test()
```

---

## 🚨 **緊急回退計劃**

### **如果出現嚴重錯誤**
1. **立即停止**: 不要繼續修改
2. **記錄錯誤**: 複製完整錯誤訊息
3. **檢查備份**: 確認備份文件完整
4. **回退步驟**:
   ```bash
   # 回退到上一個工作版本
   git checkout HEAD~1
   # 或者手動恢復備份文件
   ```
5. **分析問題**: 使用檢查清單找出問題原因
6. **修正後重試**: 解決問題後重新開始

### **常見錯誤快速修復**
```python
# ModuleNotFoundError: No module named 'xxx'
# 檢查: Import 路徑是否正確，__init__.py 是否存在

# AttributeError: 'xxx' object has no attribute 'yyy'
# 檢查: 是否忘記加 self.，方法名是否正確

# NameError: name 'xxx' is not defined
# 檢查: 變數是否已定義，Import 是否遺漏
```

---

**檢查清單使用說明**:
- ✅ 表示已檢查通過
- ❌ 表示檢查失敗，需要修正
- ⏳ 表示正在檢查中
- ⚠️ 表示需要特別注意