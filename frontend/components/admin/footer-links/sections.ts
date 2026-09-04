import type { FooterLinkSection } from "@/lib/api/modules/footer-links";

/** Admin-facing copy for each footer block managed by FooterLinksPanel. */
export interface FooterSectionCopy {
  title: string;
  description: string;
  emptyHint: string;
  addDialogDescription: string;
  titlePlaceholderZh: string;
  titlePlaceholderEn: string;
}

export const FOOTER_SECTION_COPY: Record<FooterLinkSection, FooterSectionCopy> = {
  related: {
    title: "相關連結",
    description:
      "顯示在網頁最下方的連結，可放外部網址或上傳檔案（PDF 等），並可拖曳排序。",
    emptyHint: "目前尚無相關連結，點擊「新增」建立。",
    addDialogDescription: "新增後會顯示在網頁最下方的「相關連結」區塊。",
    titlePlaceholderZh: "例如：獎學金申請指南",
    titlePlaceholderEn: "Scholarship Guide",
  },
  policy: {
    title: "政策連結",
    description:
      "顯示在網頁最下方版權列旁的小字連結（例如隱私權政策、使用條款、無障礙聲明、網站地圖），可放外部網址或上傳檔案，並可拖曳排序。預設項目為隱藏，請先設定正確網址再顯示。",
    emptyHint: "目前尚無政策連結，點擊「新增」建立。",
    addDialogDescription: "新增後會顯示在網頁最下方版權列旁的小字連結。",
    titlePlaceholderZh: "例如：隱私權政策",
    titlePlaceholderEn: "Privacy Policy",
  },
};
