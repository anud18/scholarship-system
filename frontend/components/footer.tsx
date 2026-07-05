"use client";
import { useEffect, useState } from "react";
import { Separator } from "@/components/ui/separator";
import { ExternalLink, GraduationCap, ChevronDown } from "lucide-react";

interface FooterProps {
  locale?: "zh" | "en";
}

export function Footer({ locale = "zh" }: FooterProps) {
  const currentYear = new Date().getFullYear();
  // Render the "Last updated" date only after mount to avoid SSR/CSR
  // hydration mismatches caused by the server and client rendering with
  // different locale-formatted strings (or different system clocks crossing
  // a date boundary). The footer's other content stays SSR-rendered.
  const [lastUpdated, setLastUpdated] = useState<string>("");
  useEffect(() => {
    setLastUpdated(
      new Date().toLocaleDateString(locale === "zh" ? "zh-TW" : "en-US")
    );
  }, [locale]);

  return (
    <footer className="bg-gradient-to-br from-nycu-navy-50 to-nycu-blue-50 border-t-4 border-nycu-blue-600 mt-12">
      <div className="container mx-auto px-4 py-8 md:py-12">
        <div className="grid gap-8 md:grid-cols-4">
          {/* University Logo & System Info */}
          <div className="md:col-span-2">
            <div className="flex items-start gap-4 mb-6">
              {/* NYCU Logo */}
              <div className="flex-shrink-0">
                <div className="nycu-gradient w-20 h-20 rounded-xl flex items-center justify-center nycu-shadow">
                  <GraduationCap className="text-white h-10 w-10" />
                </div>
              </div>
              <div>
                <h3 className="font-bold text-xl text-nycu-navy-800 mb-2">
                  {locale === "zh"
                    ? "國立陽明交通大學"
                    : "National Yang Ming Chiao Tung University"}
                </h3>
                <div className="space-y-1">
                  <p className="text-nycu-navy-700 font-semibold">
                    {locale === "zh" ? "教務處" : "Office of Academic Affairs"}
                  </p>
                  <p className="text-nycu-navy-600 text-sm">
                    {locale === "zh"
                      ? "獎學金申請與審核系統"
                      : "NYCU Admissions Scholarship System"}
                  </p>
                  <p className="text-nycu-navy-500 text-xs font-medium">
                    {locale === "zh" ? "版本 v1.0.0" : "Version v1.0.0"}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white/60 rounded-lg p-4 nycu-border">
              <p className="text-nycu-navy-700 text-sm leading-relaxed">
                {locale === "zh"
                  ? "本系統由教務處開發維護，提供學生獎學金申請、教授推薦、行政審核等完整流程管理，致力於提升獎學金作業效率與透明度，落實學校「智慧校園」願景。"
                  : "This system is developed and maintained by the Office of Academic Affairs, providing comprehensive management for student scholarship applications, professor recommendations, and administrative reviews, committed to improving efficiency and transparency in scholarship operations."}
              </p>
            </div>
          </div>

          {/* Contact Information — collapsible on mobile via native <details>
              (closed by default below md). Above md it renders flat without
              a disclosure widget so desktop layout is unchanged. */}
          <details className="group [&_summary::-webkit-details-marker]:hidden" open>
            <summary className="flex items-center justify-between cursor-pointer md:cursor-default list-none">
              <h4 className="font-bold text-nycu-navy-800 text-lg">
                {locale === "zh" ? "聯絡資訊" : "Contact Information"}
              </h4>
              <ChevronDown
                className="h-5 w-5 text-nycu-navy-600 transition-transform group-open:rotate-180 md:hidden"
                aria-hidden="true"
              />
            </summary>
          </details>

          {/* Related Links — same collapsible pattern as Contact Information. */}
          <details className="group [&_summary::-webkit-details-marker]:hidden" open>
            <summary className="flex items-center justify-between cursor-pointer md:cursor-default list-none">
              <h4 className="font-bold text-nycu-navy-800 text-lg">
                {locale === "zh" ? "相關連結" : "Related Links"}
              </h4>
              <ChevronDown
                className="h-5 w-5 text-nycu-navy-600 transition-transform group-open:rotate-180 md:hidden"
                aria-hidden="true"
              />
            </summary>
            <div className="space-y-3 mt-4">
              <a
                href="https://www.nycu.edu.tw"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-nycu-navy-700 hover:text-nycu-blue-600 transition-colors group"
              >
                <ExternalLink className="h-4 w-4 group-hover:scale-110 transition-transform" />
                {locale === "zh" ? "陽明交大首頁" : "NYCU Homepage"}
              </a>

              <a
                href="https://aa.nycu.edu.tw/"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-nycu-navy-700 hover:text-nycu-blue-600 transition-colors group"
              >
                <ExternalLink className="h-4 w-4 group-hover:scale-110 transition-transform" />
                {locale === "zh" ? "教務處" : "Academic Affairs"}
              </a>

              <a
                href="https://portal.nycu.edu.tw"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-nycu-navy-700 hover:text-nycu-blue-600 transition-colors group"
              >
                <ExternalLink className="h-4 w-4 group-hover:scale-110 transition-transform" />
                {locale === "zh" ? "NYCU Portal" : "NYCU Portal"}
              </a>

              <a
                href="#"
                className="flex items-center gap-2 text-sm text-nycu-navy-700 hover:text-nycu-blue-600 transition-colors group"
              >
                <ExternalLink className="h-4 w-4 group-hover:scale-110 transition-transform" />
                {locale === "zh" ? "獎學金申請指南" : "Scholarship Guide"}
              </a>

              <a
                href="#"
                className="flex items-center gap-2 text-sm text-nycu-navy-700 hover:text-nycu-blue-600 transition-colors group"
              >
                <ExternalLink className="h-4 w-4 group-hover:scale-110 transition-transform" />
                {locale === "zh" ? "常見問題" : "FAQ"}
              </a>

              <a
                href="#"
                className="flex items-center gap-2 text-sm text-nycu-navy-700 hover:text-nycu-blue-600 transition-colors group"
              >
                <ExternalLink className="h-4 w-4 group-hover:scale-110 transition-transform" />
                {locale === "zh" ? "系統操作手冊" : "User Manual"}
              </a>
            </div>
          </details>
        </div>

        <Separator className="my-8 bg-nycu-blue-200" />

        {/* Bottom Copyright & Policies */}
        <div className="flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="text-sm text-nycu-navy-600">
            <p className="font-medium">
              © {currentYear}{" "}
              {locale === "zh"
                ? "國立陽明交通大學教務處"
                : "NYCU Office of Academic Affairs"}
              .{locale === "zh" ? " 版權所有" : " All rights reserved"}.
            </p>
            <p className="text-xs text-nycu-navy-500 mt-1">
              {locale === "zh"
                ? "本系統遵循個人資料保護法相關規定"
                : "This system complies with Personal Data Protection Act"}
            </p>
          </div>

          <div className="flex gap-6 text-xs text-nycu-navy-500">
            <a href="#" className="hover:text-nycu-blue-600 transition-colors">
              {locale === "zh" ? "隱私權政策" : "Privacy Policy"}
            </a>
            <a href="#" className="hover:text-nycu-blue-600 transition-colors">
              {locale === "zh" ? "使用條款" : "Terms of Use"}
            </a>
            <a href="#" className="hover:text-nycu-blue-600 transition-colors">
              {locale === "zh" ? "無障礙聲明" : "Accessibility"}
            </a>
            <a href="#" className="hover:text-nycu-blue-600 transition-colors">
              {locale === "zh" ? "網站地圖" : "Sitemap"}
            </a>
          </div>
        </div>

        {/* System Status */}
        <div className="mt-6 pt-6 border-t border-nycu-blue-200">
          <div className="flex items-center justify-between text-xs text-nycu-navy-400">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <span>
                {locale === "zh" ? "系統正常運行" : "System Operational"}
              </span>
              <span>
                {locale === "zh" ? "最後更新" : "Last Updated"}:{" "}
                {/* lastUpdated is empty during SSR; populated on client mount
                    to avoid hydration mismatch (locale/timezone-dependent). */}
                <span suppressHydrationWarning>{lastUpdated || " "}</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
