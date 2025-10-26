"use client";

import { useMemo } from "react";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";

interface JsonDiffViewerProps {
  oldValue: any;
  newValue: any;
  locale?: "zh" | "en";
}

export function JsonDiffViewer({
  oldValue,
  newValue,
  locale = "zh",
}: JsonDiffViewerProps) {
  const oldString = useMemo(() => {
    if (!oldValue) return "";
    return typeof oldValue === "string"
      ? oldValue
      : JSON.stringify(oldValue, null, 2);
  }, [oldValue]);

  const newString = useMemo(() => {
    if (!newValue) return "";
    return typeof newValue === "string"
      ? newValue
      : JSON.stringify(newValue, null, 2);
  }, [newValue]);

  const styles = {
    variables: {
      light: {
        diffViewerBackground: "#fafafa",
        diffViewerColor: "#212529",
        addedBackground: "#e6ffed",
        addedColor: "#24292e",
        removedBackground: "#ffeef0",
        removedColor: "#24292e",
        wordAddedBackground: "#acf2bd",
        wordRemovedBackground: "#fdb8c0",
        addedGutterBackground: "#cdffd8",
        removedGutterBackground: "#ffdce0",
        gutterBackground: "#f7f7f7",
        gutterBackgroundDark: "#f3f3f3",
        highlightBackground: "#fffbdd",
        highlightGutterBackground: "#fff5b1",
      },
    },
    line: {
      padding: "10px 2px",
      fontSize: "13px",
      lineHeight: "20px",
      fontFamily:
        'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
    },
    gutter: {
      padding: "10px 8px",
      minWidth: "50px",
      textAlign: "right" as const,
      fontSize: "12px",
    },
    marker: {
      padding: "10px 4px",
      fontSize: "13px",
    },
    wordDiff: {
      padding: "2px 0",
      borderRadius: "2px",
    },
    contentText: {
      wordBreak: "break-word" as const,
    },
  };

  if (!oldString && !newString) {
    return (
      <div className="text-center py-4 text-sm text-gray-500">
        {locale === "zh" ? "無變更資料" : "No changes"}
      </div>
    );
  }

  return (
    <div className="rounded-lg overflow-hidden border border-gray-200 shadow-sm">
      <ReactDiffViewer
        oldValue={oldString}
        newValue={newString}
        splitView={false}
        compareMethod={DiffMethod.WORDS}
        useDarkTheme={false}
        hideLineNumbers={false}
        showDiffOnly={true}
        styles={styles}
        leftTitle={locale === "zh" ? "變更前" : "Before"}
        rightTitle={locale === "zh" ? "變更後" : "After"}
      />
    </div>
  );
}
