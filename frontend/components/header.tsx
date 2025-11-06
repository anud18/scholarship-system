"use client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LanguageSwitcher } from "@/components/language-switcher";
import { NationalityFlag } from "@/components/nationality-flag";
import { NotificationButton } from "@/components/notification-button";
import { getTranslation } from "@/lib/i18n";
import { LogOut, GraduationCap } from "lucide-react";

interface UserType {
  id: string;
  name: string;
  email: string;
  role: "student" | "professor" | "college" | "admin" | "super_admin";
  nycu_id?: string;
  nationality?: string;
}

interface HeaderProps {
  user: UserType;
  locale: "zh" | "en";
  onLocaleChange: (locale: "zh" | "en") => void;
  showLanguageSwitcher?: boolean;
  onLogout: () => void;
}

export function Header({
  user,
  locale,
  onLocaleChange,
  showLanguageSwitcher = false,
  onLogout,
}: HeaderProps) {
  const t = (key: string) => getTranslation(locale, key);

  const getRoleBadge = (role: string) => {
    const roleMap = {
      student: {
        label: user.role === "student" ? t("roles.student") : "學生",
        variant: "default" as const,
      },
      professor: { label: "教授", variant: "default" as const },
      college: { label: "學院", variant: "default" as const },
      admin: { label: "管理員", variant: "destructive" as const },
      super_admin: { label: "系統管理員", variant: "destructive" as const },
    };
    return (
      roleMap[role as keyof typeof roleMap] || {
        label: role,
        variant: "outline" as const,
      }
    );
  };

  const roleBadge = getRoleBadge(user.role);

  return (
    <header className="sticky top-0 z-50 academic-header backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-6">
            {/* NYCU Logo and Branding */}
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-3">
                {/* NYCU Logo */}
                <div className="nycu-gradient h-12 w-12 rounded-lg flex items-center justify-center nycu-shadow">
                  <GraduationCap className="h-7 w-7 text-white" />
                </div>
                <div className="flex flex-col">
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-xl nycu-text-gradient">
                      NYCU
                    </span>
                    <span className="text-sm font-medium text-nycu-navy-600 whitespace-nowrap">
                      {locale === "zh"
                        ? "陽明交大"
                        : "National Yang Ming Chiao Tung University"}
                    </span>
                  </div>
                  <span className="text-xs text-nycu-navy-500 font-medium">
                    {locale === "zh" ? "教務處" : "Academic Affairs"}
                  </span>
                </div>
              </div>
            </div>

            {/* System Title */}
            <div className="hidden md:block border-l border-nycu-blue-200 pl-6">
              <h1 className="font-semibold text-lg text-nycu-navy-800">
                {locale === "zh"
                  ? "獎學金申請與簽核系統"
                  : "NYCU Admissions Scholarship System"}
              </h1>
              <p className="text-sm text-nycu-navy-600">
                {locale === "zh"
                  ? "NYCU Admissions Scholarship System"
                  : "Admissions Scholarship Management"}
              </p>
            </div>

            {/* Role Badge */}
            <Badge
              variant={roleBadge.variant}
              className="hidden sm:inline-flex whitespace-nowrap"
            >
              {roleBadge.label}
            </Badge>

            {/* Nationality Flag */}
            {user.nationality && (
              <div className="hidden sm:block">
                <NationalityFlag
                  countryCode={user.nationality}
                  locale={locale}
                  showLabel={false}
                />
              </div>
            )}
          </div>

          <div className="flex items-center gap-4">
            {/* Language Switcher - only for students */}
            {showLanguageSwitcher && (
              <LanguageSwitcher
                currentLocale={locale}
                onLocaleChange={onLocaleChange}
              />
            )}

            {/* Notifications */}
            <NotificationButton locale={locale} />

            {/* User Info Display */}
            <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/50 border border-gray-200">
              {/* Nationality Flag */}
              {user.nationality && (
                <NationalityFlag
                  countryCode={user.nationality}
                  locale={locale}
                  showLabel={false}
                />
              )}

              {/* User Info Text */}
              <div className="hidden md:flex flex-col px-2">
                <span className="text-sm font-semibold text-gray-900">
                  {user.name}
                </span>
                {user.nycu_id && (
                  <span className="text-xs text-gray-500">
                    {user.nycu_id}
                  </span>
                )}
              </div>
              {/* Logout Button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={onLogout}
                className="gap-2"
              >
                <LogOut className="h-4 w-4" />
                <span className="hidden sm:inline">
                  {user.role === "student" ? t("nav.logout") : "登出"}
                </span>
              </Button>
            </div>


          </div>
        </div>
      </div>
    </header>
  );
}
