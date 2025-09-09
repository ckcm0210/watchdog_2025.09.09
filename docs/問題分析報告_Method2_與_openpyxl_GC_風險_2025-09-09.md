# 方法二（直接監控）與 0x80000003 崩潰風險：分析與驗證計劃（草稿）

此文件為「活文件」。你每次提出質疑/補充，我會把問答整合回本文件並標註版本歷史。

---

## 1. 背景與目標
- 現象：在 Python 3.11/3.12 環境下，方法二（跳過啟動時建立 baseline，直接監控）偶發 0x80000003（STATUS_BREAKPOINT）崩潰；崩潰點多在 GC（垃圾回收）階段，堆疊顯示 xml.etree.ElementTree 的 C 擴展，呼叫源頭為 openpyxl 讀取工作表。
- 目標：
  1) 界定高風險路徑與誘因（openpyxl + ElementTree + GC 時機）。
  2) 釐清方法一 vs 方法二的差異（實際影響的是「時機與併發」而非流程大變）。
  3) 設定層的 A/B 驗證計劃（先不改碼）。
  4) 列出可行技術路線（最小風險 → 根本解）與風險控制。

---

## 2. 關鍵證據（Crash log 摘要）
- 兩份崩潰報告一致顯示：
  - Current thread: Garbage-collecting（GC 期間）
  - xml.etree.ElementTree._start/feed/iterator → openpyxl.worksheet._reader.parse/_read_only._cells_by_row → core/excel_parser.dump_excel_cells_with_timeout
- 推論：在 GC 時機觸發到 ElementTree（C 擴展）內部的不一致（或 openpyxl 使用路徑的脆弱點），導致 0x80000003。

---

## 3. 程式中使用 openpyxl 的關鍵位置
- 核心熱路徑：core/excel_parser.dump_excel_cells_with_timeout
  - 先 copy_to_cache（只讀快取檔）
  - safe_load_workbook(read_only=...)
  - for 每張工作表：ws.iter_rows(values_only=False) 掃 cell，用 get_cell_formula/pretty_formula 取公式；值則交由 VALUE_ENGINE（polars/polars_xml/xml/pandas）提供
  - 若 ENABLE_FORMULA_VALUE_CHECK=True：額外再開一次 data_only=True 的 workbook，專門把「公式格」的 cached value 補齊
- 其他：
  - get_excel_last_author：正常讀 zip core.xml；失敗時 fallback openpyxl（仍是讀「快取檔」，風險低）
  - utils/timeline_excel.py：寫 Timeline.xlsx（寫入風險較低，但仍是 openpyxl）

---

## 4. 方法一 vs 方法二（流程與「寫檔時間窗口」澄清）
- 相同點：兩者都只對「快取副本」做讀取與解析，非讀原檔。
- 實際差異不在「流程內容」而在「時機與併發」：
  - 方法一（建立 baseline）：通常在啟動或批次階段，序列化處理一批檔案；多數時候不會恰好撞正使用者正在編輯（寫檔）某檔案的瞬間；Watchdog 尚未開始大量事件輪詢/觸發。
  - 方法二（直接監控）：事件一來即「立刻比較」，時間點貼近 Excel 儲存；雖然 copy_to_cache 有 mtime 穩定檢查，但仍接近上游寫入階段。此外，之後還會啟動 ActivePollingHandler 做輪詢，整體「觸發更頻」且時間更貼近變更源頭。
- 「寫檔時間窗口」是指：上游（Excel/其他進程）剛完成寫檔或仍在 flush/同步，其後你在極短時間內拉取快取副本並解析。即使讀的是快取檔，時間點仍然很貼近「剛剛寫完」的區間（尤其網路盤/SMB），這段期間最容易暴露底層庫的脆弱點；加上 Python 3.11/3.12 的 GC 時機更積極，更容易在解析期間被 GC 打斷。

> 總結：流程幾乎一致，但「方法一多在較平靜時間、單線序列」，「方法二多在高頻變更即時觸發」，這就是觀感上穩定度的差別來源。

---

## 5. 設定項：ENABLE_FORMULA_VALUE_CHECK 的意義
- 功能目的：對「公式儲存格」再讀取一次 data_only=True 的工作簿，把 Excel 緩存值（cached value）補齊。
- 解決的問題：
  - 若只比較公式字串，可能出現外部參照刷新造成的假差異；讀 cached value 可用來判斷實際顯示值有無改變（配合抑制策略）。
- 真正的行為：
  1) 第一階段已經用 VALUE_ENGINE 提供每格的 value/cached_value（polars_xml/xml 亦會給「值」）
  2) 只有在「有公式格」且 VALUE_ENGINE 未提供 cached_value 時，且公式格數量不超過 MAX_FORMULA_VALUE_CELLS，上述設定才會觸發第二次以 data_only=True 讀檔，把這些地址的 cached value 補齊。
- 風險：這一步會再次打開工作簿（仍是快取檔），因此它是另一個 openpyxl 熱點。

---

## 6. 關於 gc.set_threshold(10000, 100, 100) 與物件數量的估算
- 估算原則：
  - openpyxl 在 iter_rows(values_only=False) 會產生/訪問大量 Cell 物件；「掃描範圍」接近工作表 used range（近似 max_row*max_column），而非只有非空格。
  - 我們保留在結果中的，是「有公式或有值」的地址；對每個地址會保留一個小 dict（formula/value/cached_value/external_ref）+ 字串/數值等。
- 粗略級別估算：
  - 掃描（臨時物件）：O(已掃 cell 數) 的 Cell/字串等臨時物件，數量可達數十萬～百萬級（大表）。
  - 保留（結果物件）：O(非空或有公式的 cell 數)；例如一張 10 萬格中 1 萬格非空，則保留級別 ~1 萬個 dict + 對應字串/數值。
- 意義：Python 3.11/3.12 的 GC 更積極，這種「大量短生命週期物件」在解析期間容易觸發 GC，撞上 ElementTree 的 C 擴展銷毀階段，就更容易出現 0x80000003。

---

## 7. 驗證計劃（先不改碼）
- 目的：驗證「openpyxl 讀公式」是否為主要誘因。
- 建議設定（臨時）：
  - FORMULA_ONLY_MODE = False
  - TRACK_FORMULA_CHANGES = False
  - ENABLE_FORMULA_VALUE_CHECK = False
  - VALUE_ENGINE = "polars_xml"（或 "xml"）
- 預期：方法二在高頻事件時顯著更穩定。
- 可選：暫停 Timeline.xlsx 輸出（讓它 fallback CSV）以移除寫入 openpyxl 的參與。

---

## 8. 技術路線（不立即實施，先討論）
1) 最小風險快速緩解（保守）：
   - 在 dump_excel_cells_with_timeout 內，對 openpyxl 載入與遍歷區塊加「局部 GC 守護」：進入前 gc.disable()，完成後 gc.enable() + gc.collect()。
   - 確認環境使用 lxml 解析器（已設 OPENPYXL_LXML=True）。
   - 優點：改動小；風險低；常見能顯著降低 crash 機率。

2) 根本方案 A：XML 直接抽公式（FORMULA_ENGINE=xml）
   - 不再用 openpyxl 讀公式，改為解析 sheetN.xml 的 <f> 節點：
     - 普通公式：<f> 內就是公式字串（保真度高，無需還原）
     - 共享公式（shared）：主儲存格有 <f t="shared" si="0" ref="A1:C1">=A1+1</f>；其餘同組儲存格只有 <f t="shared" si="0"/>，需根據主公式「相對位移」展開
     - 陣列公式（array）：<f t="array" ref="...">...</f>
   - 優點：完全避開 openpyxl；公式文字保真（無需「還原」）。
   - 挑戰：shared formula 的展開邏輯較複雜（需做相對引用位移）。

3) 根本方案 B：子進程隔離 openpyxl
   - 把「讀公式」放到短命子進程，主程式只拿結果 JSON。
   - 若子進程崩潰，主程式無感；可重試/降級成僅值比較。
   - 可配合「工作佇列＋最大並行數」：例如同一時間最多 2～4 個子進程，避免 30 檔同時開 30 進程。

4) 其他補強
   - copy_to_cache 的穩定檢查（你目前設定：
     - COPY_STABILITY_CHECKS=5, INTERVAL=1.0s, MAX_WAIT=12.0s）
   - 拉長建議（高頻環境）：例如 7～10 次、間隔 1.0～1.5s、最大等待 20s；
   - 影響範圍：只會阻塞「該檔案」的快取複製流程，不會卡死全程式。

---

## 9. 你的問題與解答（Q&A 第一輪）

Q1.「寫檔時間窗口」到底指邊個檔案？我哋係 copy 到自己個 folder 先再讀，方法一/二之後流程應該一樣。
- A：指的是「你啟動解析快取副本的時機」相對於「上游（Excel）剛完成寫檔」的時間差。雖然讀的是快取檔，但 copy_to_cache 的啟動點越貼近原檔剛寫完，越容易暴露底層庫在 GC 時機的脆弱點。方法一通常在較「平靜」時段批次跑；方法二則是事件來就即時跑（整體更貼近「剛寫完」）。流程內容幾乎一致，但時序與觸發頻度不同。

Q2.gc.set_threshold(10000, 100, 100) 想估計一下程式大概產生幾多物件？
- A：粗略估算：掃描階段會臨時產生 O(掃描格數) 的 Cell/字串等；保留階段 O(非空/有公式格數)。例如一張表 10 萬格、其中 1 萬格非空，保留結果約 1 萬個 cell dict（每個含 3～4 個欄位）+ 對應字串/數值；臨時物件可能到數十萬級。Python 3.11/3.12 的 GC 較積極，這種型態容易在解析間被 GC 觸發。

Q3.「ENABLE_FORMULA_VALUE_CHECK → data_only 的 pass」再解釋一次？
- A：此設定用於「補齊公式格的顯示值」。若第一階段 VALUE_ENGINE 未提供 cached_value，且公式格數量在上限內，就會第二次用 data_only=True 開 workbook，逐個公式地址讀 cached value。目的是減少外部參照刷新造成的假變更。這一步是另一個 openpyxl 熱點。

Q4.方法一話「檔案穩定時讀取」係指讀原檔定快取檔？方法一/二唔都係讀快取檔？而且 baseline.json 係比較依據，兩者都一樣。
- A：係，兩者都讀「快取檔」。我講「穩定」係指上游編輯/寫入活動的節奏同你啟動解析的時間差。方法一多在使用者未在高頻操作時序列化跑完；方法二就係事件觸發即時比對，整體時間點更貼近上游變更，所以更容易踩中 GC/ElementTree 的弱點。baseline.json 的用途一致無誤。

Q5.喺你屋企（Win11）重現唔到，公司（Win10）先有：會唔會係 OS/硬件差異？
- A：可能性高。影響因素包括：
  - OS（Win10 vs Win11）對底層記憶體/文件系統行為差異
  - Python 發行版（Anaconda vs 原生）、xml 模組 C 擴展版本
  - 是否裝有 lxml（openpyxl 會優先用）
  - 磁碟/網路盤（SMB）的寫入/同步行為；公司內網壓力更大
  - 硬件性能高時，GC/解析耗時更短，較難踩到同一個臨界時序

Q6.最小風險方案會唔會反而引入不穩定？
- A：建議先做「設定層驗證」（不改碼）。若要改碼，局部 GC 守護屬「包圍式」保護，變動小、容易回退；亦可加開關（例如：ENABLE_GC_GUARD_FOR_OPENPYXL），預設關閉，手動啟用再驗證。

Q7.HTML 報表「公式差異」唔好逐字 diff，要呈現有意義段落（整段刪/整段加）
- A：已加入代辦清單。可採「前綴保留 + 差異段落標注」或「token/區塊級 diff」策略，避免逐字亂序視覺噪音。

Q8.XML 抽公式會唔會比 openpyxl 更好？「openpyxl 讀到 123 要還原」嗰啲情況點？
- A：對「公式字串」本身，XML 會更加「保真」（直接取 <f> 內容），毋須還原；openpyxl 的「還原」多發生在「值」而非「公式字串」。真正難點在「shared formula 展開」。

Q9.乜係 shared formula？點解「展開」要小心？
- A：共享公式例：
  ```xml
  <!-- 主儲存格 A1 -->
  <c r="A1"><f t="shared" si="0" ref="A1:C1">=A1+1</f></c>
  <!-- 同組其他儲存格（B1/C1）只標示共享編號，無公式字串 -->
  <c r="B1"><f t="shared" si="0"/></c>
  <c r="C1"><f t="shared" si="0"/></c>
  ```
  - openpyxl 會幫你把 B1/C1 的實際公式計算出來（相對位移）。
  - 如果自己解析 XML，要根據主公式把引用（例如 A1）按相對位移轉換到 B1/C1 的版本，否則你會只見到主公式，其他格公式變空（或全都顯示主格公式，造成假差異）。

Q10.子進程隔離會唔會一堆事件就開一堆進程？
- A：我們會設計「工作佇列＋最大並行數」：例如最多 2～4 個子進程，同時只處理有限數量檔案；其餘排隊。並且做「同檔去重」（同一時間只保留該檔最新任務）。唔會 30 檔就起 30 個進程。

Q11.拉長 copy 穩定檢查要幾多？會唔會卡實整個程式？
- A：目前設定：CHECKS=5、INTERVAL=1.0s、MAX_WAIT=12s。高頻時可考慮 CHECKS=7～10、INTERVAL=1.0～1.5s、MAX_WAIT=20s。這只會延遲「該檔案」的快取複製，不會阻塞其他檔案或主循環。

---

## 10. 代辦清單（Backlog）
- [ ] HTML 報表「公式差異」提升：由逐字改為段落/區塊級 diff（可選 token 化）
- [ ] 設定層驗證腳本/說明：一鍵切換關閉公式追蹤進行穩定性驗證
- [ ] （可選）GC 守護開關：ENABLE_GC_GUARD_FOR_OPENPYXL（預設關閉）
- [ ] （可選）FORMULA_ENGINE=xml 的設計與 PoC（含 shared/array 展開）
- [ ] （可選）openpyxl 子進程隔離 + 佇列 + 併發上限
- [ ] （可選）Timeline.xlsx 輸出開關（允許暫停 Excel 寫入）

---

## 11. 建議的下一步（不改碼先驗證）
1) 用設定關閉公式相關：FORMULA_ONLY_MODE=False、TRACK_FORMULA_CHANGES=False、ENABLE_FORMULA_VALUE_CHECK=False；VALUE_ENGINE=polars_xml。
2) 在公司環境跑方法二（高頻改動場景），觀察是否穩定。
3) 如穩定 → 初步確立 openpyxl 讀公式為主要誘因；再討論採用「GC 守護」或「FORMULA_ENGINE=xml / 子進程隔離」路線。

---

## 12. Q&A 第二輪（2025-09-09）

1) 等幾耐先算過咗「寫檔時間窗口」？copy_to_cache 同 GC 有冇直接關係？
- 建議：維持而家預設（COPY_STABILITY_CHECKS=5, INTERVAL=1.0s, MAX_WAIT=12s）。在高頻環境可微調至 7～10 次、間隔 1.0～1.5s、最大 20s。
- 只會阻塞「該檔案」的複製，不會卡住其他檔案或整個程式。
- 與 GC 的關係：copy_to_cache 係文件層面「何時開始讀」，GC 崩潰係解析（openpyxl/ElementTree）時被 GC 打斷。兩者獨立，但「越貼近上游剛寫完」越容易踩中底層 Bug 的時序。

2) ENABLE_FORMULA_VALUE_CHECK 會「第二次」讀檔，可否合併為一次？
- 用 openpyxl 階段：一個 workbook 無法同時兼顧 formula 與 data_only 緩存值（data_only=True 會令 .value 變成 cached 值，拿不到 formula 物件）。故需要第二次打開（僅在需要時）。
- 真正「一次完成」的方法：用 XML 引擎直接讀 sheetN.xml，<f> 取公式、<v>/<is> 取值，一次把兩者取齊（避開 openpyxl）。

3) 乜係「假差異」？
- 例子：
  - 外部參照路徑標準化（相對→絕對、UNC 正規化），公式字串變咗但顯示值無變。
  - Excel 自動格式/日期序號↔字串之間的表示差異。
  - 共享公式從主儲存格複製到其他格，引用樣式變化但語義一致。
  - 計算引擎未重新計算（cached value 舊），只比公式會以為變更；或相反只比值會誤判。

4) 大檔案（多工作表 × 每表上千 cell）點避開 3.11/3.12 的 GC 積極？
- 策略：
  - A) 在 openpyxl 解析區塊加「局部 GC 守護」（disable→解析→enable→collect）。
  - B) 改用 XML 引擎讀公式與值，完全避開 openpyxl。
  - C) 限制併發與排隊（同時最多 N 個任務；同檔去重）。
  - D) 保持你已有的批次/分批讀取（batch）與快取穩定檢查。

5) 點解唔以「記憶體用量」而係以「物件數量」決定 GC？
- Python 的代際 GC 係以「分配/存活的物件計數」來觸發，而唔係 RSS 記憶體。記憶體用量我哋可額外監看（utils/memory.py 已有）用作節流，但 GC 本身的觸發機制係計數導向。

6) 公式引擎比較（估算）
- openpyxl（讀公式）：
  - 優點：自帶共享/陣列公式展開、與 Excel 語義一致、功能成熟。
  - 缺點：在 3.11/3.12 + ElementTree/GC 較易中招；物件多、較慢、較吃記憶體；可能需第二次 data_only pass。
  - 適用：需要完全對齊 openpyxl 語義，且環境穩定時。
- XML（直接讀 <f>/<v>）：
  - 優點：快速、低記憶體；一次取齊公式與值；避開 openpyxl（穩定）。
  - 缺點：需自行實作 shared/array 公式展開；部分邊緣案例（名稱、3D 引用、表格結構參照）要額外處理。
  - 適用：監控/比對場景；更重視穩定與效能。
- 效能預期：XML 引擎一般較 openpyxl 快、佔用更少。openpyxl read_only 全表掃描在大表會偏慢。

7) 「共享公式（shared formula）」再舉例
- XML 會寫：
  ```xml
  <c r="A1"><f t="shared" si="0" ref="A1:C1">=A1+1</f></c>
  <c r="B1"><f t="shared" si="0"/></c>
  <c r="C1"><f t="shared" si="0"/></c>
  ```
- 意思：A1 為主格，套用範圍 A1:C1。B1/C1 的公式要把主公式的引用按「相對位移」平移：
  - A1 的 =A1+1 → B1 變 =B1+1 → C1 變 =C1+1。
- 若範圍係 A1:C3，去到 B2（相對 +1 行 +1 列）時，A1 參照要轉成 B2，其他參照按相同位移平移。呢個「展開」需自行計算。

8) 子進程隔離會唔會爆進程數？
- 會加「工作佇列 + 最大併發（如 2～4）」同「同檔去重」。唔會 30 檔就開 30 個進程。

9) 拉長 copy 穩定檢查會唔會卡死？
- 只影響「該檔案」嘅複製流程；其他檔案事件唔受影響。

---

## 13. 設定驗證清單（公司環境，先不改碼）
- 目的：驗證 openpyxl 讀公式是否主要誘因。
- 步驟：
  1) 設定：FORMULA_ONLY_MODE=False
  2) 設定：TRACK_FORMULA_CHANGES=False
  3) 設定：ENABLE_FORMULA_VALUE_CHECK=False
  4) 設定：VALUE_ENGINE="polars_xml"（或 "xml"）
  5) （可選）暫停 Timeline.xlsx：先用 CSV 代替
  6) 於方法二（直接監控）下，對同一資料夾進行高頻修改，觀察穩定性
- 預期：崩潰顯著減少/消失 → 初步確認 openpyxl 為主因；之後再討論採用 GC 守護/FORMULA_ENGINE=xml/子進程隔離。

---

## 版本歷史（本文件會持續更新）
- v0.1（2025-09-09）：初稿，納入第一輪 Q&A。
