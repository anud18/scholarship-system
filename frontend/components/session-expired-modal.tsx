"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Locale } from "@/lib/validators";

interface SessionExpiredModalProps {
  isOpen: boolean;
  onRelogin: () => void;
  locale?: Locale;
  type?: "token_expired" | "unauthorized" | "forbidden";
}

export function SessionExpiredModal({
  isOpen,
  onRelogin,
  locale = "zh",
  type = "token_expired",
}: SessionExpiredModalProps) {
  const messages = {
    zh: {
      token_expired: {
        title: "登入已過期",
        description: "您的登入已過期，請重新登入以繼續使用系統。",
      },
      unauthorized: {
        title: "權限不足",
        description: "您沒有權限執行此操作，請聯繫管理員或重新登入。",
      },
      forbidden: {
        title: "存取被拒絕",
        description: "您無法存取此資源，請確認您的權限或重新登入。",
      },
      relogin_button: "重新登入",
    },
    en: {
      token_expired: {
        title: "Session Expired",
        description:
          "Your session has expired. Please log in again to continue.",
      },
      unauthorized: {
        title: "Unauthorized",
        description:
          "You don't have permission for this action. Please contact admin or log in again.",
      },
      forbidden: {
        title: "Access Denied",
        description:
          "You cannot access this resource. Please check your permissions or log in again.",
      },
      relogin_button: "Log In Again",
    },
  };

  const message = messages[locale][type];

  return (
    <Dialog open={isOpen} onOpenChange={() => {}}>
      <DialogContent
        className="sm:max-w-md"
        // Prevent closing by clicking outside or pressing ESC
        onEscapeKeyDown={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
              <AlertTriangle className="h-6 w-6 text-red-600" />
            </div>
            <div className="flex-1">
              <DialogTitle className="text-left text-lg font-semibold text-red-900">
                {message.title}
              </DialogTitle>
            </div>
          </div>
        </DialogHeader>
        <DialogDescription className="text-left text-base text-gray-700 pt-2">
          {message.description}
        </DialogDescription>
        <DialogFooter className="sm:justify-center mt-4">
          <Button
            onClick={onRelogin}
            className="w-full sm:w-auto bg-nycu-blue-600 hover:bg-nycu-blue-700 text-white"
            size="lg"
          >
            {messages[locale].relogin_button}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
