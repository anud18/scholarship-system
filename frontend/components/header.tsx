"use client";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import { LanguageSwitcher } from "@/components/language-switcher";
import { NationalityFlag } from "@/components/nationality-flag";
import { NotificationButton } from "@/components/notification-button";
import { getTranslation } from "@/lib/i18n";
import { LogOut, Settings, User, GraduationCap } from "lucide-react";

interface UserType {
  id: string;
  name: string;
  email: string;
  role: "student" | "professor" | "college" | "admin" | "super_admin";
  studentId?: string;
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
      professor: { label: "教授", variant: "secondary" as const },
      college: { label: "學院", variant: "secondary" as const },
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
    <header className="academic-header backdrop-blur supports-[backdrop-filter]:bg-background/60">
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
                    <span className="text-sm font-medium text-nycu-navy-600">
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
                  ? "獎學金申請與簽核作業管理系統"
                  : "NYCU Admissions Scholarship System"}
              </h1>
              <p className="text-sm text-nycu-navy-600">
                {locale === "zh"
                  ? "Scholarship Application and Approval Management"
                  : "Admissions Scholarship Management"}
              </p>
            </div>

            {/* Role Badge */}
            <Badge
              variant={roleBadge.variant}
              className="hidden sm:inline-flex"
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

          <div className="flex items-center space-x-4">
            {/* Language Switcher - only for students */}
            {showLanguageSwitcher && (
              <LanguageSwitcher
                currentLocale={locale}
                onLocaleChange={onLocaleChange}
              />
            )}

            {/* Notifications */}
            <NotificationButton locale={locale} />

            {/* User Menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="relative h-10 w-10 rounded-full"
                >
                  <Avatar className="h-10 w-10 border-2 border-nycu-blue-200">
                    <AvatarImage src="/placeholder-user.jpg" alt={user.name} />
                    <AvatarFallback className="bg-nycu-blue-50 text-nycu-blue-700 font-semibold">
                      {user.name.charAt(0)}
                    </AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-64" align="end" forceMount>
                <DropdownMenuLabel className="font-normal">
                  <div className="flex flex-col space-y-2">
                    <div className="flex items-center space-x-2">
                      <p className="text-sm font-semibold leading-none">
                        {user.name}
                      </p>
                      <Badge variant={roleBadge.variant} className="text-xs">
                        {roleBadge.label}
                      </Badge>
                    </div>
                    <p className="text-xs leading-none text-muted-foreground">
                      {user.email}
                    </p>
                    {user.studentId && (
                      <p className="text-xs leading-none text-muted-foreground">
                        {user.role === "student" && locale === "en"
                          ? "Student ID"
                          : "學號"}
                        : {user.studentId}
                      </p>
                    )}
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem>
                  <User className="mr-2 h-4 w-4" />
                  <span>
                    {user.role === "student" ? t("nav.profile") : "個人資料"}
                  </span>
                </DropdownMenuItem>
                <DropdownMenuItem>
                  <Settings className="mr-2 h-4 w-4" />
                  <span>
                    {user.role === "student" && locale === "en"
                      ? "Settings"
                      : "設定"}
                  </span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-red-600" onClick={onLogout}>
                  <LogOut className="mr-2 h-4 w-4" />
                  <span>
                    {user.role === "student" ? t("nav.logout") : "登出"}
                  </span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>
    </header>
  );
}
