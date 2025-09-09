# Excel 版本控制工具：開發總結與交接文件 (v2 - 完整版)

**文件版本:** 2.0
**更新日期:** 2025-09-07

## 1. 總覽 (Overview)

本文件旨在**鉅細無遺地**記錄「Excel 版本控制工具」的核心功能設計、技術實現細節、設計決策過程、以及未來的開發路線圖，以確保專案知識的傳承和後續開發的順利進行。

本工具的核心目標是為 Excel 檔案提供一個視覺化的版本控制與差異比較解決方案，解決傳統 Excel 協作中變更追蹤困難的痛點。

---

## 2. 核心功能：視覺化差異報告

工具最關鍵的產出是一個獨立的、無需使用者交互即可閱覽的 HTML 報告，該報告清晰地展示了 Excel 檔案在兩個版本之間的具體差異。

### 2.1. 最終範例檔案 (The Final Prototype)

所有關於視覺化報告的討論與迭代，最終成果體現在以下範例檔案中。**所有前端的開發都應以此檔案為最終的視覺和功能標準**。

- **檔案路徑:** `C:\Users\user\final_diff_report_default_view.html`

### 2.2. 視覺化呈現的詳細規格

#### 2.2.1. 智能渲染邏輯 (The "Smart" Rules)

報告的核心是 `generateDiffHtml` JavaScript 函式，它會根據以下**優先級順序**，為每一條差異記錄自動選擇最優的視覺化模式：

1.  **無變化:**
    - **觸發條件:** 舊值 (`oldStr`) 與新值 (`newStr`) 完全相同。
    - **顯示方式:** 輸出文字「無變化」。

2.  **模式 A: 並列式 (Side-by-Side)**
    - **觸發條件 (滿足其一即可):**
        - **非公式變更:** 新舊值均不以 `=` 開頭。
        - **重大結構性變更:**
            - 一個是公式，另一個是純數值/文字。
            - 兩者都是公式，但**主要函式名稱不同** (例如 `=SUM(...)` vs `=AVERAGE(...)`)。
    - **顯示方式:** 在同一行內，先顯示帶紅色刪除線的舊值，後跟帶綠色背景的新值。
    - **HTML 格式:** `<span class="diff-deleted">...</span> <span class="diff-added">...</span>`

3.  **模式 B: 行內式 (Inline / Character-level)**
    - **觸發條件:** 不滿足以上所有條件的**其他所有情況**。這通常意味著是同一個函式內部的局部修改。
    - **顯示方式:** 只對實際發生變更的字元進行標示。
    - **HTML 格式:** `...<span class="diff-deleted">D</span><span class="diff-added">E</span>...`

#### 2.2.2. 完整程式碼範例 (HTML, CSS, JS)

以下是 `final_diff_report_default_view.html` 的完整原始碼，可供開發者直接參考和使用。

```html
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <title>Final Diff Report (Default View)</title>
    <style>
        /* CSS 樣式... (此處省略以保持文件簡潔，完整版請參考原檔案) */
        body { font-family: sans-serif; max-width: 1200px; margin: auto; }
        table { width: 100%; border-collapse: collapse; table-layout: fixed; }
        th, td { border: 1px solid #ddd; padding: 12px; word-wrap: break-word; }
        .diff-deleted { background-color: #ffebe9; text-decoration: line-through; color: #c00; }
        .diff-added { background-color: #e6ffed; color: #080; }
        .mono, .visualize-cell { font-family: Consolas, 'Courier New', monospace; }
    </style>
</head>
<body>
    <h1>Excel 變更報告 (最終版 - 預設顯示)</h1>
    <table>
        <!-- 表格結構... -->
        <tbody id="report-body"></tbody>
    </table>
    <script>
        // --- 這是由 Python 注入的數據 ---
        const diffData = [ /* ... 數據陣列 ... */ ];

        // --- 核心 JavaScript 函式 ---
        function generateDiffHtml(oldStr, newStr) {
            if (oldStr === newStr) { return '<span>無變化</span>'; }
            const isOldFormula = oldStr.startsWith('=');
            const isNewFormula = newStr.startsWith('=');
            const oldFuncName = isOldFormula ? (oldStr.match(/=\\s*([A-Z_]+)\\(/i) || [])[1] : null;
            const newFuncName = isNewFormula ? (newStr.match(/=\\s*([A-Z_]+)\\(/i) || [])[1] : null;

            if (!isOldFormula || !isNewFormula || (oldFuncName && newFuncName && oldFuncName.toUpperCase() !== newFuncName.toUpperCase())) {
                return `<span class="diff-deleted">${oldStr}</span> <span class="diff-added">${newStr}</span>`;
            }
            return generateInlineDiff(oldStr, newStr);
        }

        function generateInlineDiff(text1, text2) {
            // ... 基於 LCS 的精細比較演算法 ...
            // (此處省略以保持文件簡潔，完整版請參考原檔案)
            const dp = Array(text1.length + 1).fill(null).map(() => Array(text2.length + 1).fill(0));
            for (let i = 1; i <= text1.length; i++) {
                for (let j = 1; j <= text2.length; j++) {
                    if (text1[i - 1] === text2[j - 1]) {
                        dp[i][j] = dp[i - 1][j - 1] + 1;
                    } else {
                        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
                    }
                }
            }
            let i = text1.length, j = text2.length;
            let result = [];
            while (i > 0 || j > 0) {
                if (i > 0 && j > 0 && text1[i - 1] === text2[j - 1]) {
                    result.unshift(text1[i - 1]);
                    i--; j--;
                } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
                    result.unshift(`<span class="diff-added">${text2[j - 1]}</span>`);
                    j--;
                } else if (i > 0 && (j === 0 || dp[i][j - 1] < dp[i - 1][j])) {
                    result.unshift(`<span class="diff-deleted">${text1[i - 1]}</span>`);
                    i--;
                }
            }
            return result.join('');
        }

        // --- 頁面初始化 ---
        window.onload = function() {
            const tbody = document.getElementById('report-body');
            diffData.forEach((item) => {
                const tr = document.createElement('tr');
                const visualDiffHtml = generateDiffHtml(item.oldVal, item.newVal);
                tr.innerHTML = `
                    <td>${item.sheet}</td>
                    <td class="mono">${item.address}</td>
                    <td class="mono">${item.oldVal}</td>
                    <td class="mono">${item.newVal}</td>
                    <td class="visualize-cell">${visualDiffHtml}</td>
                `;
                tbody.appendChild(tr);
            });
        };
    </script>
</body>
</html>
```

### 2.3. Python 整合指南 (How to Generate This Report)

要在現有的 Python 程式碼中生成上述的自包含 HTML 報告，應遵循以下步驟：

1.  **準備差異數據:** 在 Python 中完成兩個版本 `baseline.json` 的比較後，將結果整理成一個串列 (list)，其結構與 JavaScript 中的 `diffData` 完全對應。

    ```python
    # 假設這是你比較後得到的結果
    diff_list = [
        {'sheet': 'Sheet1', 'address': 'A1', 'oldVal': '100', 'newVal': '250'},
        {'sheet': 'Sheet1', 'address': 'C5', 'oldVal': '=SUM(C1:C4)', 'newVal': '=AVERAGE(D1:D4)'},
        # ... more diffs
    ]
    ```

2.  **序列化數據為 JSON:** 使用 `json` 模組將 Python 串列轉換為 JSON 字串。

    ```python
    import json
    # ensure_ascii=False 確保中文字元能正確顯示
    json_data_string = json.dumps(diff_list, ensure_ascii=False)
    ```

3.  **創建 HTML 模板:** 將 HTML 檔案的內容作為一個 Python 字串模板。使用 `f-string` 或其他模板引擎 (如 Jinja2) 將上一步生成的 JSON 字串**注入**到 `<script>` 標籤中。

    ```python
    # 這是一個簡化的 f-string 模板
    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <!-- ... CSS 樣式 ... -->
    </head>
    <body>
        <!-- ... 表格結構 ... -->
        <script>
            // 將 Python 生成的 JSON 字串直接放在這裡
            const diffData = {json_data_string};

            // ... 完整的 JavaScript 函式 ...
        </script>
    </body>
    </html>
    """
    ```

4.  **寫入檔案:** 將最終生成的完整 HTML 字串寫入檔案，確保使用 `utf-8` 編碼。

    ```python
    with open("diff_report.html", "w", encoding="utf-8") as f:
        f.write(html_template)
    ```

---

## 3. 未來功能擴展路線圖 (待辦清單)

### 3.1. 元素讀取性能與開發建議總表

這份表格總結了各類 Excel 元素的讀取方式、性能、開發複雜度，是後續功能開發的**核心決策依據**。

| 元素 (Element) | 讀取方式          | 速度   | 是否需啟動 Excel | 開發複雜度 | 路線圖建議                                       |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **命名範圍**       | `openpyxl`          | **非常快** | 否               | 低         | **第一優先級 (Tier 1)** - 成本極低，價值高。         |
| **工作表屬性**     | `openpyxl`          | **非常快** | 否               | 低         | **第一優先級 (Tier 1)** - 例如隱藏/顯示狀態。        |
| **VBA 巨集**       | **`oletools (olevba)`** | **快**     | **否**           | 中等       | **第二優先級 (Tier 2)** - **重大突破**，避開了效能陷阱。 |
| **條件式格式**     | `openpyxl`          | 快     | 否               | 中等       | **第二優先級 (Tier 2)** - 實用性強，需設計 UI。      |
| **資料驗證**       | `openpyxl`          | 快     | 否               | 中等       | **第二優先級 (Tier 2)** - 同上。                     |
| **儲存格樣式**     | `openpyxl`          | 中等   | 否               | 高         | **第三優先級 (Tier 3)** - 價值相對較低，UI 複雜。    |
| **圖表**           | `openpyxl`          | 中等   | 否               | 高         | **第三優先級 (Tier 3)** - 資料結構複雜，需仔細設計。 |
| **樞紐分析表**     | `openpyxl`          | 中等   | 否               | 非常高     | **長期目標 (Long-term)** - 結構最複雜，暫不考慮。    |

### 3.2. 程式碼整合與架構建議

為了以**可擴展、易維護**的方式加入上述新功能，建議採用以下架構：

1.  **創建新的「元數據提取器」模組:**
    - **位置:** `core/excel_metadata_extractor.py`
    - **職責:** 專門負責讀取除了核心儲存格內容之外的所有附加資訊 (命名範圍, VBA, ...)。
    - **結構:** 建立一個 `MetadataExtractor` 類別，包含 `get_named_ranges`, `get_vba_modules` 等多個獨立方法。
    - **優點:** 實現**關注點分離**，使主比較邏輯保持乾淨，並讓新功能的添加變得模組化。

2.  **修改現有比較流程:**
    - 在主比較邏輯中 (`core/excel_comparison.py`) `import` 新的提取器。
    - 在生成 `baseline.json` 時，除了遍歷儲存格，同時呼叫提取器的方法，將獲取到的元數據一併存入 `baseline.json` 的頂層鍵中。

---

## 4. 附錄：設計決策備忘

### 4.1. 「有意義的變更 (Meaningful Change)」的定義

經過討論，我們將「有意義的變更」定義擴展為：
> **「任何由使用者直接操作，或由外部連結刷新，導致儲存格的『值』、『公式』、『類型』或『錯誤狀態』發生改變的，都視為有意義的變更。」**

此定義應作為後端比較邏輯的指導原則。

### 4.2. 關於「上下文儲存格」的顯示

- **討論:** 曾考慮過在報告中顯示變更儲存格周圍的格子，以提供上下文。
- **決策:** **決定不預設顯示上下文**。
- **原因:**
    1.  會讓自包含的 HTML 報告檔案體積劇增。
    2.  使用者可以隨時打開原始 Excel 檔案來查看完整的上下文。
    3.  保持報告的簡潔性，使其專注於**已發生變更**的資訊。

```