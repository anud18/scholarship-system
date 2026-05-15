/**
 * Verified Account Alert Component
 *
 * Displays a notification to students when they have a verified bank account.
 * Allows students to choose between using the verified account or entering a new one.
 */

'use client';

import { useState } from 'react';
import { CheckCircle, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { VerifiedAccountResponse } from '@/lib/api/modules/bank-verification';

interface VerifiedAccountAlertProps {
  verifiedAccount: VerifiedAccountResponse | null;
  onUseVerifiedAccount?: (accountNumber: string, accountHolder: string) => void;
  onEnterNewAccount?: () => void;
}

export function VerifiedAccountAlert({
  verifiedAccount,
  onUseVerifiedAccount,
  onEnterNewAccount,
}: VerifiedAccountAlertProps) {
  const [showDetails, setShowDetails] = useState(false);

  if (!verifiedAccount?.has_verified_account || !verifiedAccount.account) {
    return (
      <Alert variant="default" className="border-blue-200 bg-blue-50">
        <AlertCircle className="h-4 w-4 text-blue-600" />
        <AlertTitle className="text-blue-900">首次申請</AlertTitle>
        <AlertDescription className="text-blue-800">
          您尚未有已驗證的郵局帳號。請填寫您的郵局帳號並上傳帳本封面照片。
          管理員審核通過後，下次申請時即可直接使用。
        </AlertDescription>
      </Alert>
    );
  }

  const { account } = verifiedAccount;

  return (
    <Alert variant="default" className="border-green-200 bg-green-50">
      <CheckCircle className="h-4 w-4 text-green-600" />
      <AlertTitle className="text-green-900 flex items-center gap-2">
        您已有驗證通過的郵局帳號
        <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
          已驗證
        </Badge>
      </AlertTitle>
      <AlertDescription className="text-green-800 space-y-3">
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="font-medium">帳號：</span>
            <span className="font-mono">{account.account_number}</span>
          </div>
          <div>
            <span className="font-medium">戶名：</span>
            <span>{account.account_holder}</span>
          </div>
          <div className="col-span-2">
            <span className="font-medium">驗證日期：</span>
            <span>{new Date(account.verified_at).toLocaleDateString('zh-TW')}</span>
          </div>
        </div>

        {showDetails && account.passbook_cover_url && (
          <div className="mt-3 p-3 bg-white rounded border border-green-200">
            <p className="text-sm font-medium mb-2">帳本封面照片</p>
            {/* eslint-disable-next-line @next/next/no-img-element -- user-uploaded passbook scan, unknown aspect ratio; next/image gives no benefit with images.unoptimized */}
            <img
              src={account.passbook_cover_url}
              alt="已驗證的帳本封面"
              className="max-w-xs rounded border"
            />
          </div>
        )}

        <div className="flex gap-2 mt-4">
          <Button
            onClick={() => {
              if (onUseVerifiedAccount) {
                onUseVerifiedAccount(account.account_number, account.account_holder);
              }
            }}
            className="bg-green-600 hover:bg-green-700"
          >
            使用此帳號（不需重新驗證）
          </Button>
          <Button
            onClick={onEnterNewAccount}
            variant="outline"
            className="border-green-600 text-green-700 hover:bg-green-50"
          >
            修改帳號
          </Button>
          {account.passbook_cover_url && (
            <Button
              onClick={() => setShowDetails(!showDetails)}
              variant="ghost"
              size="sm"
              className="text-green-700"
            >
              {showDetails ? '隱藏' : '查看'}帳本封面
            </Button>
          )}
        </div>

        <p className="text-xs text-green-700 mt-2">
          💡 使用已驗證帳號可加快申請審核速度。如需修改帳號，需重新上傳帳本封面並等待驗證。
        </p>
      </AlertDescription>
    </Alert>
  );
}
