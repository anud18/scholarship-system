"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ArrowDown,
  ArrowUp,
  ListChecks,
  Loader2,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import apiClient from "@/lib/api";
import type {
  ApplicationNotices,
  LocalizedApplicationNotices,
} from "@/lib/api/modules/system-settings";
import { toast } from "sonner";

const LOCALES: Array<{ key: "zh" | "en"; label: string }> = [
  { key: "zh", label: "中文" },
  { key: "en", label: "English" },
];

const MAX_ITEMS = 30;

// Items get a stable client-side key so React tracks identity across
// reordering — index keys would make inputs reuse the wrong DOM state.
type EditableItem = { key: string; title: string; content: string };
type EditableLocalized = {
  items: EditableItem[];
  important_notice: string;
};
type EditableNotices = { zh: EditableLocalized; en: EditableLocalized };

let itemKeyCounter = 0;
const nextItemKey = () => `notice-item-${++itemKeyCounter}`;

function toEditable(notices: ApplicationNotices): EditableNotices {
  const localize = (l: LocalizedApplicationNotices): EditableLocalized => ({
    important_notice: l.important_notice,
    items: l.items.map((item) => ({ ...item, key: nextItemKey() })),
  });
  return { zh: localize(notices.zh), en: localize(notices.en) };
}

function toPayload(notices: EditableNotices): ApplicationNotices {
  const strip = (l: EditableLocalized): LocalizedApplicationNotices => ({
    important_notice: l.important_notice,
    items: l.items.map(({ title, content }) => ({ title, content })),
  });
  return { zh: strip(notices.zh), en: strip(notices.en) };
}

export function ApplicationNoticesPanel() {
  const [notices, setNotices] = useState<EditableNotices | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const load = async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const res = await apiClient.systemSettings.applicationNotices.get();
      if (res.success && res.data) {
        setNotices(toEditable(res.data));
        setDirty(false);
      } else {
        setLoadFailed(true);
        toast.error(res.message || "載入注意事項失敗");
      }
    } catch {
      setLoadFailed(true);
      toast.error("載入注意事項失敗");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const mutateLocale = (
    locale: "zh" | "en",
    mutate: (draft: EditableLocalized) => EditableLocalized
  ) => {
    setNotices((prev) => {
      if (!prev) return prev;
      return { ...prev, [locale]: mutate(prev[locale]) };
    });
    setDirty(true);
  };

  const updateItem = (
    locale: "zh" | "en",
    index: number,
    patch: Partial<{ title: string; content: string }>
  ) =>
    mutateLocale(locale, (draft) => ({
      ...draft,
      items: draft.items.map((item, i) =>
        i === index ? { ...item, ...patch } : item
      ),
    }));

  const addItem = (locale: "zh" | "en") =>
    mutateLocale(locale, (draft) => ({
      ...draft,
      items: [...draft.items, { key: nextItemKey(), title: "", content: "" }],
    }));

  const removeItem = (locale: "zh" | "en", index: number) =>
    mutateLocale(locale, (draft) => ({
      ...draft,
      items: draft.items.filter((_, i) => i !== index),
    }));

  const moveItem = (locale: "zh" | "en", index: number, direction: -1 | 1) =>
    mutateLocale(locale, (draft) => {
      const target = index + direction;
      if (target < 0 || target >= draft.items.length) return draft;
      const items = [...draft.items];
      [items[index], items[target]] = [items[target], items[index]];
      return { ...draft, items };
    });

  const validate = (data: EditableNotices): string | null => {
    for (const { key, label } of LOCALES) {
      const localized = data[key];
      if (localized.items.length === 0) {
        return `${label}至少需要一項注意事項`;
      }
      if (!localized.important_notice.trim()) {
        return `${label}的重要提醒不可為空`;
      }
      for (let i = 0; i < localized.items.length; i++) {
        if (!localized.items[i].title.trim()) {
          return `${label}第 ${i + 1} 項的標題不可為空`;
        }
        if (!localized.items[i].content.trim()) {
          return `${label}第 ${i + 1} 項的內容不可為空`;
        }
      }
    }
    return null;
  };

  const save = async () => {
    if (!notices) return;
    const error = validate(notices);
    if (error) {
      toast.error(error);
      return;
    }
    setSaving(true);
    try {
      const res = await apiClient.systemSettings.applicationNotices.update(
        toPayload(notices)
      );
      if (res.success) {
        toast.success("注意事項已更新，學生端將立即看到新內容");
        setDirty(false);
      } else {
        toast.error(res.message || "儲存失敗");
      }
    } catch {
      toast.error("儲存失敗");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="overflow-hidden border-gray-200/80 shadow-sm">
      <CardHeader className="bg-gradient-to-br from-gray-50 to-white border-b">
        <div className="flex items-start gap-4">
          <div className="rounded-xl bg-nycu-navy-900 p-3 shadow-sm">
            <ListChecks className="h-6 w-6 text-white" />
          </div>
          <div className="flex-1">
            <CardTitle className="text-xl text-nycu-navy-900">
              獎學金申請注意事項
            </CardTitle>
            <CardDescription className="mt-1">
              編輯學生申請流程第一步顯示的注意事項與重要提醒（中英文）。儲存後學生端即套用新內容。
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-6">
        {loading ? (
          <div className="flex items-center justify-center py-10 text-gray-500">
            <Loader2 className="h-5 w-5 mr-2 animate-spin" />
            載入中...
          </div>
        ) : loadFailed || !notices ? (
          <div className="flex flex-col items-center gap-3 py-10 text-sm text-gray-500">
            <p>無法載入注意事項內容</p>
            <Button variant="outline" size="sm" onClick={load}>
              重新載入
            </Button>
          </div>
        ) : (
          <div className="space-y-6">
            <Tabs defaultValue="zh">
              <TabsList className="grid w-full max-w-xs grid-cols-2">
                {LOCALES.map(({ key, label }) => (
                  <TabsTrigger key={key} value={key}>
                    {label}
                  </TabsTrigger>
                ))}
              </TabsList>

              {LOCALES.map(({ key }) => {
                const localized = notices[key];
                return (
                  <TabsContent key={key} value={key} className="space-y-6 mt-4">
                    <div className="space-y-2">
                      <Label
                        htmlFor={`important-notice-${key}`}
                        className="font-semibold text-nycu-navy-900"
                      >
                        重要提醒
                      </Label>
                      <Textarea
                        id={`important-notice-${key}`}
                        value={localized.important_notice}
                        onChange={(e) =>
                          mutateLocale(key, (draft) => ({
                            ...draft,
                            important_notice: e.target.value,
                          }))
                        }
                        maxLength={2000}
                        rows={3}
                        placeholder="顯示於注意事項頂部的醒目提醒"
                      />
                    </div>

                    <div className="space-y-4">
                      <Label className="font-semibold text-nycu-navy-900">
                        注意事項條目
                      </Label>
                      {localized.items.map((item, index) => (
                        <div
                          key={item.key}
                          className="rounded-lg border border-gray-200 p-4 space-y-3 bg-white"
                        >
                          <div className="flex items-center gap-2">
                            <div className="flex-shrink-0 w-7 h-7 rounded-full bg-nycu-blue-100 text-nycu-blue-700 flex items-center justify-center font-semibold text-sm">
                              {index + 1}
                            </div>
                            <Input
                              value={item.title}
                              onChange={(e) =>
                                updateItem(key, index, {
                                  title: e.target.value,
                                })
                              }
                              maxLength={100}
                              placeholder="標題（例：申請資格）"
                              className="flex-1"
                            />
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => moveItem(key, index, -1)}
                              disabled={index === 0}
                              title="上移"
                            >
                              <ArrowUp className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => moveItem(key, index, 1)}
                              disabled={index === localized.items.length - 1}
                              title="下移"
                            >
                              <ArrowDown className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => removeItem(key, index)}
                              disabled={localized.items.length <= 1}
                              className="text-red-500 hover:text-red-600 hover:bg-red-50"
                              title="刪除"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                          <Textarea
                            value={item.content}
                            onChange={(e) =>
                              updateItem(key, index, {
                                content: e.target.value,
                              })
                            }
                            maxLength={2000}
                            rows={3}
                            placeholder="內容說明（支援換行）"
                          />
                        </div>
                      ))}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => addItem(key)}
                        disabled={localized.items.length >= MAX_ITEMS}
                      >
                        <Plus className="h-4 w-4 mr-1.5" />
                        新增條目
                      </Button>
                    </div>
                  </TabsContent>
                );
              })}
            </Tabs>

            <div className="flex items-center justify-end gap-3 pt-4 border-t">
              {dirty && (
                <span className="text-sm text-amber-600">尚有未儲存的變更</span>
              )}
              <Button
                onClick={save}
                disabled={saving || !dirty}
                className="nycu-gradient text-white"
              >
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                    儲存中...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4 mr-1.5" />
                    儲存變更
                  </>
                )}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
