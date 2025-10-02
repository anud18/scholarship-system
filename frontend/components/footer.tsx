"use client";
import { Separator } from "@/components/ui/separator";
import { Mail, Phone, MapPin, ExternalLink, GraduationCap } from "lucide-react";

interface FooterProps {
  locale?: "zh" | "en";
}

export function Footer({ locale = "zh" }: FooterProps) {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="bg-gradient-to-br from-nycu-navy-50 to-nycu-blue-50 border-t-4 border-nycu-blue-600 mt-12">
      <div className="container mx-auto px-4 py-12">
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
                      ? "獎學金申請與簽核作業管理系統"
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

          {/* Contact Information */}
          <div>
            <h4 className="font-bold text-nycu-navy-800 mb-4 text-lg">
              {locale === "zh" ? "聯絡資訊" : "Contact Information"}
            </h4>
            <div className="space-y-6">
              {/* 交大校區 */}
              <div className="space-y-3">
                <h5 className="font-semibold text-nycu-navy-700 flex items-center gap-2">
                  <span className="inline-block w-2 h-2 bg-nycu-blue-600 rounded-full"></span>
                  {locale === "zh" ? "交大校區" : "Chiao Tung Campus"}
                </h5>
                <div className="flex items-start gap-3 text-sm text-nycu-navy-700">
                  <MapPin className="h-5 w-5 text-nycu-blue-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="font-medium">
                      {locale === "zh"
                        ? "30010 新竹市大學路1001號"
                        : "1001 University Road, Hsinchu City 30010"}
                    </p>
                    <p className="text-nycu-navy-600 text-xs mt-1">
                      {locale === "zh"
                        ? "科學1館1樓(教務處各單位) / 浩然圖書資訊中心8樓(教務長室)"
                        : "Science Building 1, 1F (Academic Affairs Units) / Library & Information Center, 8F (Dean's Office)"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 text-sm text-nycu-navy-700">
                  <Phone className="h-5 w-5 text-nycu-blue-600 flex-shrink-0" />
                  <div>
                    <p className="font-medium">(03) 571-2121</p>
                    <p className="text-nycu-navy-600 text-xs">
                      {locale === "zh"
                        ? "分機: 31666(註冊), 31668(課務), 31391(招生), 31751, 31752(處本部)"
                        : "Ext: 31666(Registration), 31668(Curriculum), 31391(Admission), 31751, 31752(Main Office)"}
                    </p>
                  </div>
                </div>
              </div>

              {/* 陽明校區 */}
              <div className="space-y-3">
                <h5 className="font-semibold text-nycu-navy-700 flex items-center gap-2">
                  <span className="inline-block w-2 h-2 bg-nycu-orange-600 rounded-full"></span>
                  {locale === "zh" ? "陽明校區" : "Yang Ming Campus"}
                </h5>
                <div className="flex items-start gap-3 text-sm text-nycu-navy-700">
                  <MapPin className="h-5 w-5 text-nycu-orange-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="font-medium">
                      {locale === "zh"
                        ? "11221 台北市北投區立農街二段155號"
                        : "No. 155, Sec. 2, Linong St., Beitou District, Taipei City 11221"}
                    </p>
                    <p className="text-nycu-navy-600 text-xs mt-1">
                      {locale === "zh"
                        ? "行政大樓3樓"
                        : "Administration Building, 3F"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 text-sm text-nycu-navy-700">
                  <Phone className="h-5 w-5 text-nycu-orange-600 flex-shrink-0" />
                  <div>
                    <p className="font-medium">(02) 2826-7000</p>
                    <p className="text-nycu-navy-600 text-xs">
                      {locale === "zh"
                        ? "分機: 62203(註冊), 62038(課務), 62299(招生), 62310(實習), 62022(處本部)"
                        : "Ext: 62203(Registration), 62038(Curriculum), 62299(Admission), 62310(Internship), 62022(Main Office)"}
                    </p>
                  </div>
                </div>
              </div>

              {/* Email */}
              <div className="flex items-center gap-3 text-sm text-nycu-navy-700 pt-2">
                <Mail className="h-5 w-5 text-nycu-blue-600 flex-shrink-0" />
                <div>
                  <p className="font-medium">oaa@nycu.edu.tw</p>
                  <p className="text-nycu-navy-600 text-xs">
                    {locale === "zh" ? "教務處信箱" : "Academic Affairs Email"}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Related Links */}
          <div>
            <h4 className="font-bold text-nycu-navy-800 mb-4 text-lg">
              {locale === "zh" ? "相關連結" : "Related Links"}
            </h4>
            <div className="space-y-3">
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
          </div>
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
                {new Date().toLocaleDateString(
                  locale === "zh" ? "zh-TW" : "en-US"
                )}
              </span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
