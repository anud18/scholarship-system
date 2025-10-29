# useScholarshipData Hook 使用指南

## 簡介

`useScholarshipData` 是一個基於 SWR 的自訂 Hook，用於管理獎學金資料和子類型翻譯。它提供集中的資料訪問、自動快取和各種查詢的 helper functions。

## 為什麼使用 SWR？

- ✅ **減少 API 呼叫**：24小時快取策略
- ✅ **自動同步**：背景重新驗證保持資料新鮮
- ✅ **簡化狀態管理**：自動處理 loading/error/data 狀態
- ✅ **重複使用削除**：多個組件訪問相同資料只會發起一次請求
- ✅ **離線支援**：保留先前資料在網路不穩定時

## 基本使用

### 簡單示例

```typescript
'use client';

import { useScholarshipData } from '@/hooks/use-scholarship-data';

export function MyComponent() {
  const { scholarships, isLoading, error } = useScholarshipData('admin');

  if (isLoading) return <div>載入中...</div>;
  if (error) return <div>錯誤：{error.message}</div>;

  return (
    <div>
      {scholarships.map(scholarship => (
        <div key={scholarship.id}>
          {scholarship.name}
        </div>
      ))}
    </div>
  );
}
```

### 使用 Helper Functions

```typescript
import { useScholarshipData } from '@/hooks/use-scholarship-data';

export function ApplicationCard({ scholarshipId }: { scholarshipId: number }) {
  const { getScholarshipName, isLoading } = useScholarshipData('admin');

  if (isLoading) return <div>載入中...</div>;

  const scholarshipName = getScholarshipName(scholarshipId);

  return (
    <div>
      <h3>{scholarshipName}</h3>
    </div>
  );
}
```

### 中英文切換

```typescript
import { useLanguagePreference } from '@/hooks/use-language-preference';
import { useScholarshipData } from '@/hooks/use-scholarship-data';

export function ScholarshipList() {
  const { locale } = useLanguagePreference();
  const { scholarships, isLoading } = useScholarshipData('admin');

  if (isLoading) return <div>Loading...</div>;

  return (
    <ul>
      {scholarships.map(scholarship => (
        <li key={scholarship.id}>
          {locale === 'zh' ? scholarship.name : scholarship.name_en || scholarship.name}
        </li>
      ))}
    </ul>
  );
}
```

## 進階使用

### 查詢子類型翻譯

```typescript
import { useScholarshipData } from '@/hooks/use-scholarship-data';

export function SubTypeDisplay() {
  const { subTypeTranslations, getSubTypeName, isLoading } = useScholarshipData('college');

  if (isLoading) return <div>載入中...</div>;

  // 獲取單個翻譯
  const domesticName = getSubTypeName('domestic', 'zh');

  // 獲取所有翻譯
  const allZhTranslations = getAllSubTypeNames('zh');

  return (
    <div>
      <p>國內學生: {domesticName}</p>
    </div>
  );
}
```

### 批量查詢和過濾

```typescript
import { useScholarshipData, batchTranslateSubTypes } from '@/hooks/use-scholarship-data';

export function ScholarshipFilter() {
  const { scholarships, getScholarshipByCode, isLoading } = useScholarshipData('admin');

  if (isLoading) return <div>載入中...</div>;

  // 按代碼查詢
  const scholarship = getScholarshipByCode('MERIT');

  // 批量翻譯
  const subTypes = ['domestic', 'overseas', 'international'];
  const translated = batchTranslateSubTypes(subTypes, subTypeTranslations, 'zh');

  return (
    <div>
      {/* render */}
    </div>
  );
}
```

### 手動刷新資料

```typescript
import { useScholarshipData } from '@/hooks/use-scholarship-data';

export function AdminPanel() {
  const { scholarships, refresh, isLoading } = useScholarshipData('admin');

  const handleUpdateScholarship = async (id: number, data: any) => {
    try {
      // 更新獎學金
      await api.updateScholarship(id, data);
      // 刷新資料
      await refresh();
    } catch (error) {
      console.error('更新失敗:', error);
    }
  };

  return (
    <button onClick={() => refresh()}>
      {isLoading ? '重新整理中...' : '重新整理資料'}
    </button>
  );
}
```

## API 參考

### Hook 簽名

```typescript
useScholarshipData(role?: 'admin' | 'college')
```

### 返回值

```typescript
{
  // 資料
  scholarships: ScholarshipData[];
  subTypeTranslations: { zh: Record<string, string>; en: Record<string, string> };
  data: ScholarshipDataAll | undefined;

  // 狀態
  isLoading: boolean;
  error: Error | undefined;

  // 操作
  refresh: () => Promise<void>;

  // 查詢函數
  getScholarshipName(id: number, locale?: 'zh' | 'en'): string;
  getScholarshipByCode(code: string): ScholarshipData | null;
  getScholarshipById(id: number): ScholarshipData | null;
  getSubTypeName(code: string, locale?: 'zh' | 'en'): string;
  getAllSubTypeNames(locale?: 'zh' | 'en'): Record<string, string>;
}
```

### Helper Functions

#### `getScholarshipName(id, scholarships, locale?)`

```typescript
// 直接使用 hook 的方法
const { getScholarshipName } = useScholarshipData('admin');
const name = getScholarshipName(1, 'zh');

// 或使用獨立 helper
import { getScholarshipName } from '@/hooks/use-scholarship-data';
const name = getScholarshipName(1, scholarships, 'zh');
```

#### `getSubTypeName(code, translations, locale?)`

```typescript
import { getSubTypeName } from '@/hooks/use-scholarship-data';
const name = getSubTypeName('domestic', translations, 'zh');
```

#### `batchTranslateSubTypes(codes, translations, locale?)`

```typescript
import { batchTranslateSubTypes } from '@/hooks/use-scholarship-data';
const names = batchTranslateSubTypes(
  ['domestic', 'overseas'],
  translations,
  'zh'
);
```

## 效能考量

### 快取策略

```typescript
// 預設配置
{
  revalidateOnFocus: false,      // 不在重新獲得焦點時重新驗證
  revalidateOnReconnect: false,  // 不在重新連接時重新驗證
  dedupingInterval: 86400000,    // 24小時內去重
  keepPreviousData: true,        // 保留先前資料在重新驗證期間
}
```

### 優化建議

1. **避免在循環中調用 hook**
   ```typescript
   // ❌ 不好
   {items.map(item => {
     const { data } = useScholarshipData(); // 每次都調用
     return <div>{data}</div>;
   })}

   // ✅ 好
   const { scholarships } = useScholarshipData();
   return {items.map(item => (
     <div>{scholarships.find(s => s.id === item.id)}</div>
   ))}
   ```

2. **在頂級組件使用**
   ```typescript
   // ✅ 在頁面或布局中調用一次
   export function ColegePage() {
     const scholarshipData = useScholarshipData('college');
     return <ScholarshipContent data={scholarshipData} />;
   }
   ```

3. **使用 React.memo 避免不必要重新渲染**
   ```typescript
   const ScholarshipItem = React.memo(({ scholarship }) => (
     <div>{scholarship.name}</div>
   ));
   ```

## 角色差異

### Admin 角色
```typescript
const adminData = useScholarshipData('admin');
// 使用 /api/v1/admin/scholarships/sub-type-translations
```

### College 角色
```typescript
const collegeData = useScholarshipData('college');
// 使用 /api/v1/college-review/sub-type-translations
```

### 不指定角色
```typescript
const data = useScholarshipData();
// 使用預設的 admin API
```

## 錯誤處理

```typescript
import { useScholarshipData } from '@/hooks/use-scholarship-data';

export function SafeScholarshipDisplay() {
  const { scholarships, isLoading, error } = useScholarshipData('admin');

  if (error) {
    return (
      <div className="error">
        <p>無法載入獎學金資料</p>
        <button onClick={refresh}>重試</button>
      </div>
    );
  }

  if (isLoading) {
    return <div>載入中...</div>;
  }

  if (scholarships.length === 0) {
    return <div>沒有可用的獎學金</div>;
  }

  return <ScholarshipList items={scholarships} />;
}
```

## 常見問題

### Q1: 資料多久更新一次？

A: 預設為 24 小時。如果需要更頻繁的更新，可以手動調用 `refresh()` 函數。

### Q2: 如何強制重新獲取資料？

A: 調用返回的 `refresh()` 函數：
```typescript
const { refresh } = useScholarshipData();
await refresh();
```

### Q3: 可以在伺服器端使用嗎？

A: 不行，這是客戶端 hook。使用 'use client' 指令。

### Q4: 如何同時獲取多個角色的資料？

A: 多次調用 hook，每個角色一次：
```typescript
const adminData = useScholarshipData('admin');
const collegeData = useScholarshipData('college');
```

## 遷移指南

### 從舊模式遷移

**之前：**
```typescript
const [scholarships, setScholarships] = useState([]);
const [loading, setLoading] = useState(true);

useEffect(() => {
  fetchScholarships().then(data => {
    setScholarships(data);
    setLoading(false);
  });
}, []);
```

**之後：**
```typescript
const { scholarships, isLoading } = useScholarshipData('admin');
```

## 相關資源

- [SWR 文檔](https://swr.vercel.app/)
- [React Hooks 文檔](https://react.dev/reference/react)
- [use-reference-data hook](./use-reference-data.ts) - 類似的參考資料 hook
