# useScholarshipData Hook - 快速入門指南

## 🚀 5 分鐘快速開始

### 1. 基本使用（自動偵測用戶角色）✨

```typescript
'use client';

import { useScholarshipData } from '@/hooks/use-scholarship-data';

export function MyComponent() {
  // ✅ 推薦！自動偵測當前用戶角色
  const { scholarships, isLoading } = useScholarshipData();

  if (isLoading) return <div>載入中...</div>;

  return (
    <ul>
      {scholarships.map(s => (
        <li key={s.id}>{s.name}</li>
      ))}
    </ul>
  );
}
```

### 1b. 明確指定角色（可選）

```typescript
// 如果需要明確指定
const data = useScholarshipData(true, 'admin');  // 使用 Admin API
const data = useScholarshipData(true, 'college'); // 使用 College API
```

### 2. 查詢特定獎學金

```typescript
const { getScholarshipName } = useScholarshipData('admin');
const name = getScholarshipName(1, 'zh');  // 返回中文名稱
```

### 3. 查詢子類型翻譯

```typescript
const { getSubTypeName } = useScholarshipData('college');
const subTypeName = getSubTypeName('domestic', 'zh');  // 國內學生
```

## 📋 完整 API

### Hook 調用

```typescript
const {
  scholarships,                    // 獎學金陣列
  subTypeTranslations,             // 子類型翻譯對象
  isLoading,                       // 是否載入中
  error,                           // 錯誤信息
  refresh,                         // 手動刷新函數

  // 查詢方法
  getScholarshipName(id, locale),  // 根據 ID 獲取名稱
  getScholarshipByCode(code),      // 根據代碼查詢
  getScholarshipById(id),          // 根據 ID 查詢
  getSubTypeName(code, locale),    // 獲取子類型名稱
  getAllSubTypeNames(locale),      // 獲取所有翻譯
} = useScholarshipData('admin' | 'college');
```

### Helper Functions

```typescript
import {
  getScholarshipName,
  getSubTypeName,
  batchTranslateSubTypes,
} from '@/hooks/use-scholarship-data';

// 獲取單個獎學金名稱
const name = getScholarshipName(1, scholarships, 'zh');

// 獲取單個子類型名稱
const subTypeName = getSubTypeName('domestic', translations, 'zh');

// 批量翻譯
const names = batchTranslateSubTypes(['domestic', 'overseas'], translations, 'zh');
```

## 🎯 常見用途

### ✅ 顯示獎學金清單

```typescript
const { scholarships, isLoading } = useScholarshipData('admin');

return (
  {scholarships.map(s => <div key={s.id}>{s.name}</div>)}
);
```

### ✅ 獲取獎學金名稱

```typescript
const { getScholarshipName } = useScholarshipData('admin');
const name = getScholarshipName(scholarshipId);
```

### ✅ 翻譯子類型

```typescript
const { getSubTypeName } = useScholarshipData('college');
const type = getSubTypeName('domestic');  // 國內學生
```

### ✅ 支援中英文切換

```typescript
const { locale } = useLanguagePreference();
const { scholarships } = useScholarshipData('admin');

return {
  scholarships.map(s => (
    <div>
      {locale === 'zh' ? s.name : s.name_en}
    </div>
  ))
};
```

### ✅ 手動更新後刷新

```typescript
const { refresh } = useScholarshipData('admin');

const handleUpdate = async (id, data) => {
  await api.updateScholarship(id, data);
  await refresh();  // 重新載入資料
};
```

### ✅ 選擇下拉菜單

```typescript
const { scholarships, isLoading } = useScholarshipData('admin');

return (
  <select>
    <option>-- 選擇 --</option>
    {scholarships.map(s => (
      <option key={s.id} value={s.id}>
        {s.name}
      </option>
    ))}
  </select>
);
```

## ⚙️ 配置選項

### 自動角色偵測（推薦）

```typescript
// ✅ 自動偵測用戶角色（推薦做法）
// 支援所有角色：student, professor, college, admin, super_admin
useScholarshipData();
useScholarshipData(true);  // 明確啟用自動偵測

// College 用戶 → 使用 /api/v1/college-review/sub-type-translations
// Admin 用戶 → 使用 /api/v1/admin/scholarships/sub-type-translations
// 其他用戶 → 使用 /api/v1/admin/scholarships/sub-type-translations
```

### 手動指定角色（可選）

```typescript
// 禁用自動偵測，使用明確指定的角色
useScholarshipData(false, 'admin');    // 強制使用 Admin API
useScholarshipData(false, 'college');  // 強制使用 College API
```

### 快取設置

目前快取設置為固定的 24 小時。如需調整，請修改 `use-scholarship-data.ts` 中的 `dedupingInterval`。

## 🔍 查詢語法

### 按 ID 查詢

```typescript
const { getScholarshipById } = useScholarshipData('admin');
const scholarship = getScholarshipById(1);
// {id: 1, code: 'MERIT', name: '學術卓越獎學金', ...}
```

### 按代碼查詢

```typescript
const { getScholarshipByCode } = useScholarshipData('admin');
const scholarship = getScholarshipByCode('MERIT');
```

### 查詢所有翻譯

```typescript
const { getAllSubTypeNames } = useScholarshipData('college');
const zhNames = getAllSubTypeNames('zh');
// {domestic: '國內學生', overseas: '海外學生', ...}
```

## ✨ 最佳實踐

### ✅ 在頂層調用 hook

```typescript
// ✅ 好
export function Page() {
  const data = useScholarshipData('admin');
  return <Content data={data} />;
}

// ❌ 避免
export function Page() {
  return <Content />;  // 不要在深層組件調用
}
```

### ✅ 避免重複調用

```typescript
// ✅ 好 - 調用一次，傳遞給多個組件
const data = useScholarshipData('admin');
return (
  <Comp1 scholarships={data.scholarships} />
  <Comp2 scholarships={data.scholarships} />
);

// ❌ 避免 - 多次調用
<Comp1 /> // 內部調用 hook
<Comp2 /> // 又調用一次
```

### ✅ 使用 React.memo 優化

```typescript
const ScholarshipItem = React.memo(({ scholarship }) => (
  <div>{scholarship.name}</div>
));
```

### ✅ 處理 Loading 狀態

```typescript
const { scholarships, isLoading, error } = useScholarshipData();

if (error) return <ErrorComponent />;
if (isLoading) return <Skeleton />;
return <Content items={scholarships} />;
```

## 🐛 故障排除

### 問題：資料不更新

**解決**：手動調用 refresh()
```typescript
const { refresh } = useScholarshipData('admin');
await refresh();
```

### 問題：無法獲取翻譯

**解決**：確認角色正確
```typescript
// College 用戶
useScholarshipData('college')  // ✅

// Admin 用戶
useScholarshipData('admin')    // ✅
```

### 問題：中文名稱顯示為 undefined

**解決**：檢查 locale 參數
```typescript
// ❌ 錯誤
getScholarshipName(1)  // 預設是 'zh'

// ✅ 正確
getScholarshipName(1, 'zh')
getScholarshipName(1, 'en')
```

## 📊 性能特性

- **快取時間**：24 小時
- **重複請求削除**：同一小時內的重複請求只會發起一次
- **背景同步**：自動在背景更新資料
- **離線支援**：保留先前資料在網路不穩定時

## 🔗 相關文件

- [詳細 API 文檔](./use-scholarship-data.md)
- [使用範例](../components/examples/scholarship-data-example.tsx)
- [reference-data hook](../hooks/use-reference-data.ts) - 類似模式參考

## 📝 遷移檢查清單

如果你正在從舊代碼遷移：

- [ ] 找到所有 `useState + useEffect` 的獎學金資料獲取代碼
- [ ] 替換為 `useScholarshipData` hook
- [ ] 移除手動 loading/error 狀態管理
- [ ] 測試中英文切換
- [ ] 驗證資料快取工作正常
- [ ] 測試手動刷新功能

## 💡 進階技巧

### 結合其他 hooks

```typescript
const { scholarships } = useScholarshipData('admin');
const { locale } = useLanguagePreference();

return scholarships.map(s => ({
  id: s.id,
  label: locale === 'zh' ? s.name : s.name_en,
}));
```

### 在 Context 中使用

```typescript
const ScholarshipContext = createContext(null);

export function ScholarshipProvider({ children }) {
  const data = useScholarshipData('admin');
  return (
    <ScholarshipContext.Provider value={data}>
      {children}
    </ScholarshipContext.Provider>
  );
}
```

### 條件加載

```typescript
// 只有在需要時才加載
const shouldLoad = role === 'admin';
const { scholarships } = useScholarshipData(shouldLoad ? 'admin' : undefined);
```

---

**問題或建議？** 請檢查完整的 [API 文檔](./use-scholarship-data.md)
