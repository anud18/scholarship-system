更改分發規則，改成獎學金承辦人人工分發，以下是規則及參考設計
(hand pointing right)分發(以學院為單位)

(six-pointed star)改成獎學金承辦人人工分發
a.名單以院為單位
b.介面欄位參考下圖 (hand pointing down)
c.邊勾選獲獎獎學金類別，邊檢查是否額滿

```html
<!DOCTYPE html>
<html lang="zh-Hant"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>獎學金人工核配系統 - Scholarship Manual Distribution</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,typography"></script>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet"/>
<script>
        tailwind.config = {
            darkMode: "class",
            theme: {
                extend: {
                    colors: {
                        primary: "#1a56db",
                        "background-light": "#f8fafc",
                        "background-dark": "#0f172a",
                    },
                    fontFamily: {
                        display: ["Noto Sans TC", "sans-serif"],
                    },
                    borderRadius: {
                        DEFAULT: "0.5rem",
                    },
                },
            },
        };
        function toggleDarkMode() {
            document.documentElement.classList.toggle('dark');
        }
    </script>
<style>
        body {
            font-family: 'Noto Sans TC', sans-serif;
        }
        .table-sticky-header th {
            position: sticky;
            top: 0;
            z-index: 10;
        }::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: #cbd5e1;
            border-radius: 4px;
        }
        .dark ::-webkit-scrollbar-thumb {
            background: #475569;
        }
    </style>
</head>
<body class="bg-background-light dark:bg-background-dark text-slate-900 dark:text-slate-100 min-h-screen transition-colors duration-200">
<header class="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 sticky top-0 z-50">
<div class="max-w-[1600px] mx-auto px-4 h-16 flex items-center justify-between">
<div class="flex items-center gap-3">
<div class="bg-primary p-2 rounded-lg">
<span class="material-icons text-white">school</span>
</div>
<div>
<h1 class="font-bold text-lg leading-tight">獎學金核配管理系統</h1>
<p class="text-xs text-slate-500 dark:text-slate-400">Scholarship Manual Distribution System</p>
</div>
</div>
<div class="flex items-center gap-4">
<button class="p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors" onclick="toggleDarkMode()">
<span class="material-icons dark:hidden">dark_mode</span>
<span class="material-icons hidden dark:block">light_mode</span>
</button>
<div class="flex items-center gap-2 border-l pl-4 border-slate-200 dark:border-slate-700">
<span class="material-icons text-slate-400">account_circle</span>
<span class="text-sm font-medium">管理員 (admin)</span>
</div>
</div>
</div>
</header>
<main class="max-w-[1600px] mx-auto p-6 flex flex-col gap-6">
<div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
<div class="lg:col-span-3 bg-white dark:bg-slate-800 p-5 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700">
<div class="flex items-center gap-2 mb-4 text-primary font-bold">
<span class="material-icons text-sm">filter_alt</span>
                    篩選與搜尋
                </div>
<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
<div>
<label class="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">所屬學院</label>
<select class="w-full rounded-lg border-slate-200 dark:border-slate-700 dark:bg-slate-900 text-sm focus:ring-primary">
<option>全部學院</option>
<option>工學院 (College of Engineering)</option>
<option>理學院 (College of Science)</option>
<option>管理學院 (College of Management)</option>
<option>文學院 (College of Liberal Arts)</option>
<option>電機資訊學院 (College of EECS)</option>
</select>
</div>
<div>
<label class="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">系所名稱</label>
<input class="w-full rounded-lg border-slate-200 dark:border-slate-700 dark:bg-slate-900 text-sm focus:ring-primary" placeholder="輸入系所關鍵字" type="text"/>
</div>
<div class="flex items-end gap-2">
<div class="flex-grow">
<label class="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">學生姓名 / 學號</label>
<input class="w-full rounded-lg border-slate-200 dark:border-slate-700 dark:bg-slate-900 text-sm focus:ring-primary" placeholder="搜尋姓名或學號" type="text"/>
</div>
<button class="bg-primary text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center justify-center">
<span class="material-icons text-sm">search</span>
</button>
</div>
</div>
</div>
<div class="bg-white dark:bg-slate-800 p-5 rounded-xl shadow-lg border-2 border-primary/20 dark:border-primary/40">
<div class="flex items-center justify-between mb-4">
<div class="flex items-center gap-2 text-primary font-bold">
<span class="material-icons text-sm">analytics</span>
                        即時剩餘名額
                    </div>
<span class="text-[10px] bg-blue-100 dark:bg-blue-900/30 text-primary px-2 py-0.5 rounded-full">Auto-Sync</span>
</div>
<div class="space-y-3">
<div class="flex items-center justify-between p-2 rounded bg-slate-50 dark:bg-slate-900/50">
<span class="text-xs">112 國科會</span>
<span class="text-sm font-bold text-primary">08 / 12</span>
</div>
<div class="flex items-center justify-between p-2 rounded bg-slate-50 dark:bg-slate-900/50">
<span class="text-xs">113 國科會</span>
<span class="text-sm font-bold text-emerald-600 dark:text-emerald-400">14 / 20</span>
</div>
<div class="flex items-center justify-between p-2 rounded bg-slate-50 dark:bg-slate-900/50">
<span class="text-xs">114 國科會</span>
<span class="text-sm font-bold text-amber-600">02 / 15</span>
</div>
<div class="flex items-center justify-between p-2 rounded bg-slate-50 dark:bg-slate-900/50">
<span class="text-xs">教育部 +1</span>
<span class="text-sm font-bold text-slate-600 dark:text-slate-400">05 / 10</span>
</div>
<div class="flex items-center justify-between p-2 rounded bg-slate-50 dark:bg-slate-900/50">
<span class="text-xs">教育部 +2</span>
<span class="text-sm font-bold text-primary">03 / 08</span>
</div>
</div>
</div>
</div>
<div class="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden flex flex-col">
<div class="p-4 border-b border-slate-200 dark:border-slate-700 flex justify-between items-center">
<h2 class="font-bold flex items-center gap-2">
<span class="material-icons text-slate-400">list_alt</span>
                    學生申請名冊與核配作業
                </h2>
<div class="flex gap-2">
<button class="text-xs font-medium flex items-center gap-1 px-3 py-1.5 rounded border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700">
<span class="material-icons text-xs">download</span> 匯出 Excel
                    </button>
<button class="text-xs font-medium flex items-center gap-1 px-3 py-1.5 rounded bg-primary text-white hover:bg-blue-700">
<span class="material-icons text-xs">save</span> 儲存目前配置
                    </button>
</div>
</div>
<div class="overflow-x-auto">
<table class="w-full text-left border-collapse min-w-[1400px]">
<thead>
<tr class="bg-slate-50 dark:bg-slate-900/50 text-[13px] text-slate-600 dark:text-slate-300">
<th class="p-4 border border-slate-200 dark:border-slate-700 text-center font-bold w-16" rowspan="2">學院<br/>初審<br/>排序</th>
<th class="p-4 border border-slate-200 dark:border-slate-700 w-48 font-bold" rowspan="2">申請獎學金類別</th>
<th class="p-2 border border-slate-200 dark:border-slate-700 text-center font-bold bg-blue-50/50 dark:bg-blue-900/20 text-primary" colspan="5">獲獎獎學金類別 (核配勾選)</th>
<th class="p-4 border border-slate-200 dark:border-slate-700 font-bold" rowspan="2">學院</th>
<th class="p-4 border border-slate-200 dark:border-slate-700 font-bold" rowspan="2">系所</th>
<th class="p-4 border border-slate-200 dark:border-slate-700 text-center font-bold w-16" rowspan="2">年級</th>
<th class="p-4 border border-slate-200 dark:border-slate-700 font-bold" rowspan="2">學生中文姓名</th>
<th class="p-4 border border-slate-200 dark:border-slate-700 font-bold" rowspan="2">國籍</th>
<th class="p-4 border border-slate-200 dark:border-slate-700 font-bold text-red-500" rowspan="2">註冊入學日期<br/>(民國年.月.日)</th>
<th class="p-4 border border-slate-200 dark:border-slate-700 font-bold" rowspan="2">學號</th>
<th class="p-4 border border-slate-200 dark:border-slate-700 font-bold" rowspan="2">申請身份</th>
</tr>
<tr class="bg-blue-50/30 dark:bg-blue-900/10 text-[11px] text-center">
<th class="p-2 border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400">112國科會<br/>獎學金</th>
<th class="p-2 border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400">113國科會<br/>獎學金</th>
<th class="p-2 border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400">114國科會<br/>獎學金</th>
<th class="p-2 border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400">教育部+1<br/>獎學金</th>
<th class="p-2 border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400">教育部+2<br/>獎學金</th>
</tr>
</thead>
<tbody class="text-sm">
<tr class="hover:bg-slate-50 dark:hover:bg-slate-700/50 border-b border-slate-200 dark:border-slate-700 transition-colors">
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center font-bold">1</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 leading-snug">
<div class="text-[11px] opacity-80">1. 國科會博士生獎學金</div>
<div class="text-[11px] opacity-80">2. 教育部博士生獎學金</div>
</td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input checked="" class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700">工學院</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700">機械工程學系</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center">博一</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 font-medium">王曉明</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-slate-500">中華民國</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center tabular-nums">112.09.15</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 tabular-nums">D11204001</td>
<td class="p-4 text-xs font-semibold text-blue-600 dark:text-blue-400">112續領</td>
</tr>
<tr class="hover:bg-slate-50 dark:hover:bg-slate-700/50 border-b border-slate-200 dark:border-slate-700 transition-colors">
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center font-bold">2</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 leading-snug">
<div class="text-[11px] opacity-80">1. 國科會博士生獎學金</div>
</td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input checked="" class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700">理學院</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700">物理學系</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center">博二</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 font-medium">李建國</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-slate-500">中華民國</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center tabular-nums">113.02.20</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 tabular-nums">D11308022</td>
<td class="p-4 text-xs font-semibold text-emerald-600 dark:text-emerald-400">113續領</td>
</tr>
<tr class="hover:bg-slate-50 dark:hover:bg-slate-700/50 border-b border-slate-200 dark:border-slate-700 transition-colors">
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center font-bold">3</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 leading-snug">
<div class="text-[11px] opacity-80">3. 教育部博士生獎學金</div>
</td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input checked="" class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700">管理學院</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700">財務金融學系</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center">博一</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 font-medium">張艾琳</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-slate-500">馬來西亞</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center tabular-nums">114.09.01</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 tabular-nums">D11412005</td>
<td class="p-4 text-xs font-semibold text-amber-600">114新申請</td>
</tr>
<tr class="hover:bg-slate-50 dark:hover:bg-slate-700/50 border-b border-slate-200 dark:border-slate-700 transition-colors">
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center font-bold">4</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 leading-snug">
<div class="text-[11px] opacity-80">1. 國科會博士生獎學金</div>
<div class="text-[11px] opacity-80">2. 教育部博士生獎學金</div>
</td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input checked="" class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700">電機資訊學院</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700">資訊工程學系</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center">博三</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 font-medium">陳思妤</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-slate-500">中華民國</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center tabular-nums">112.09.12</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 tabular-nums">D11201018</td>
<td class="p-4 text-xs font-semibold text-blue-600 dark:text-blue-400">112續領</td>
</tr>
<tr class="hover:bg-slate-50 dark:hover:bg-slate-700/50 border-b border-slate-200 dark:border-slate-700 transition-colors">
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center font-bold">5</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 leading-snug">
<div class="text-[11px] opacity-80">1. 國科會博士生獎學金</div>
</td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-2 border-r border-slate-200 dark:border-slate-700 text-center"><input checked="" class="rounded text-primary focus:ring-primary w-5 h-5" type="checkbox"/></td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700">工學院</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700">化學工程學系</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center">博一</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 font-medium">吳美玲</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-slate-500">越南</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 text-center tabular-nums">114.02.15</td>
<td class="p-4 border-r border-slate-200 dark:border-slate-700 tabular-nums">D11403009</td>
<td class="p-4 text-xs font-semibold text-amber-600">114新申請</td>
</tr>
</tbody>
</table>
</div>
<div class="p-4 bg-slate-50 dark:bg-slate-900/50 flex flex-wrap items-center justify-between gap-4 border-t border-slate-200 dark:border-slate-700">
<div class="text-xs text-slate-500 dark:text-slate-400">
                    顯示 1 至 5 筆，共 128 筆紀錄
                </div>
<div class="flex items-center gap-2">
<button class="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors disabled:opacity-30" disabled="">
<span class="material-icons text-sm">chevron_left</span>
</button>
<button class="w-8 h-8 rounded bg-primary text-white text-xs font-bold">1</button>
<button class="w-8 h-8 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-medium">2</button>
<button class="w-8 h-8 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-medium">3</button>
<span class="px-1 text-slate-400">...</span>
<button class="w-8 h-8 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-medium">26</button>
<button class="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">
<span class="material-icons text-sm">chevron_right</span>
</button>
</div>
</div>
</div>
<div class="bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800/50 p-4 rounded-lg flex gap-3">
<span class="material-icons text-blue-500">info</span>
<div class="text-xs text-blue-800 dark:text-blue-300 leading-relaxed">
<p class="font-bold mb-1">使用說明：</p>
<ul class="list-disc list-inside space-y-1">
<li>請根據「學院初審排序」與「申請獎學金類別」手動勾選欲核配之獎項。</li>
<li>系統將即時計算右上方「剩餘名額」，若該項額度用罄將無法繼續勾選。</li>
<li>核配完成後請務必點擊「儲存目前配置」以更新資料庫。</li>
<li>申請身份分為：112續領、113續領、114新申請。</li>
</ul>
</div>
</div>
</main>
<footer class="mt-12 py-8 text-center text-slate-400 text-xs border-t border-slate-200 dark:border-slate-800">
        © 2024 獎學金分配管理系統 v2.0.4 | 建議使用 Chrome 瀏覽器以獲得最佳體驗
    </footer>
<script>
        document.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
            checkbox.addEventListener('change', function() {
                // Here we would normally trigger an AJAX call to update the real-time sidebar
                // For this UI demo, it's just visual interaction.
                console.log('Selection updated. Re-calculating quotas...');
            });
        });
    </script>

</body></html>
```