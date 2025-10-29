# Audit Trail Components

操作紀錄元件 - 現代簡約設計風格的審計日誌系統

## 📦 元件結構

```
audit-trail/
├── index.ts                    # 導出檔案
├── AuditLogItem.tsx           # 單個日誌項目（可折疊）
├── AuditLogFilters.tsx        # 篩選和搜尋面板
├── JsonDiffViewer.tsx         # JSON 變更對比顯示器
└── README.md                  # 本文件
```

## ✨ 主要功能

### 1. 可折疊的詳細資訊
- 預設顯示摘要：動作類型、描述、用戶、時間
- 點擊展開查看完整資訊：
  - HTTP 請求詳情（方法、URL）
  - IP 位址
  - 變更前後對比（JSON diff）
  - 錯誤訊息（若有）

### 2. 篩選和搜尋
- **全文搜尋**：搜尋描述、用戶名稱、IP 位址、URL
- **動作類型篩選**：多選標籤式篩選
- **即時過濾**：自動更新顯示結果
- **結果計數**：顯示符合條件的紀錄數量

### 3. JSON 變更對比
- 使用 `react-diff-viewer-continued` 實現
- 支援 JSON 美化顯示
- 高亮顯示：
  - 🟢 新增內容（綠色背景）
  - 🔴 刪除內容（紅色背景）
  - 🟡 修改內容（黃色標記）
- 行號顯示、語法高亮

### 4. 現代簡約視覺設計
- **圓角卡片**：`rounded-xl` 大圓角設計
- **柔和陰影**：`shadow-sm` 和 `hover:shadow-md`
- **漸層背景**：標題區域使用漸層背景
- **留白空間**：充足的 padding 和 margin
- **柔和配色**：使用 50 色階的背景色（如 `bg-blue-50`）
- **互動效果**：hover 時的縮放、陰影變化

## 🎨 設計系統

### 顏色編碼
| 動作類型 | 顏色 | 樣式類別 |
|---------|------|----------|
| 查看 (view) | 藍色 | `bg-blue-50 text-blue-700` |
| 更新 (update) | 琥珀色 | `bg-amber-50 text-amber-700` |
| 提交 (submit) | 紫色 | `bg-purple-50 text-purple-700` |
| 核准 (approve) | 翠綠色 | `bg-emerald-50 text-emerald-700` |
| 駁回 (reject) | 玫瑰紅 | `bg-rose-50 text-rose-700` |
| 上傳 (create) | 靛藍色 | `bg-indigo-50 text-indigo-700` |
| 刪除 (delete) | 灰色 | `bg-slate-50 text-slate-700` |
| 請求補件 | 橙色 | `bg-orange-50 text-orange-700` |

### 圖示對應
- 查看: `Eye`
- 更新: `Edit`
- 提交: `Send`
- 核准: `CheckCircle`
- 駁回: `XCircle`
- 上傳: `Upload`
- 刪除: `Trash2`
- 請求補件: `FileText`

## 📝 使用方式

### 基本使用
```tsx
import { ApplicationAuditTrail } from "@/components/application-audit-trail";

<ApplicationAuditTrail
  applicationId={123}
  locale="zh"
/>
```

### Props
```typescript
interface ApplicationAuditTrailProps {
  applicationId: number;  // 申請 ID
  locale?: "zh" | "en";   // 語言（預設: "zh"）
}
```

## 🔧 技術細節

### 依賴套件
- `react-diff-viewer-continued` - JSON diff 顯示
- `@radix-ui/react-collapsible` - 可折疊元件（via shadcn/ui）
- `lucide-react` - 圖示庫

### 效能優化
- ✅ 使用 `useMemo` 快取過濾結果
- ✅ 虛擬滾動（ScrollArea）處理大量資料
- ✅ 懶載入展開內容（CollapsibleContent）
- ✅ 避免不必要的重新渲染

### 響應式設計
- 移動端友善的布局
- 在小螢幕上隱藏次要資訊
- 使用 `hidden sm:inline` 等響應式類別

### 可訪問性
- 完整的 ARIA 標籤
- 鍵盤導航支援
- 語義化 HTML 結構
- 適當的對比度

## 🎯 未來改進方向

### 可能的擴展功能
1. **匯出功能**：匯出為 CSV、PDF 或 JSON
2. **日期範圍選擇器**：更直觀的日期篩選
3. **即時更新**：WebSocket 實時推送新紀錄
4. **分頁載入**：無限滾動或分頁
5. **進階篩選**：按時間範圍、狀態等多維度篩選
6. **書籤功能**：保存常用的篩選條件

### 動畫增強
- 可選擇添加 Framer Motion 實現：
  - 項目進入動畫（淡入 + 滑入）
  - 展開/收合的流暢過渡
  - Hover 時的微互動

## 📚 相關資源

- [Tailwind CSS 文檔](https://tailwindcss.com/docs)
- [shadcn/ui 元件庫](https://ui.shadcn.com)
- [react-diff-viewer-continued](https://github.com/aeolun/react-diff-viewer-continued)
- [Radix UI Collapsible](https://www.radix-ui.com/primitives/docs/components/collapsible)

## 🐛 已知問題

目前無已知問題。如發現問題請回報。

## 📄 授權

與主專案相同的授權條款。
