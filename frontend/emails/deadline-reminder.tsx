import { Heading, Text, Hr } from '@react-email/components';
import * as React from 'react';
import { BaseTemplate } from './_components/BaseTemplate';
import { NYCUButton } from './_components/NYCUButton';
import { InfoBox } from './_components/InfoBox';

interface DeadlineReminderProps {
  student_name?: string;
  scholarship_type?: string;
  deadline?: string;
  days_remaining?: string;
  system_url?: string;
}

export default function DeadlineReminder({
  student_name = '{{student_name}}',
  scholarship_type = '{{scholarship_type}}',
  deadline = '{{deadline}}',
  days_remaining = '3',
  system_url = '{{system_url}}',
}: DeadlineReminderProps) {
  return (
    <BaseTemplate previewText={`申請截止提醒 - ${scholarship_type}`}>
      <Heading className="text-2xl font-bold text-gray-900 mb-4 mt-0">
        ⏰ 申請截止提醒
      </Heading>

      <Text className="text-gray-700 mb-4">親愛的 {student_name} 同學您好：</Text>

      <div
        className="bg-red-50 p-6 rounded-md mb-6"
        style={{
          backgroundColor: '#fef2f2',
          padding: '24px',
          borderRadius: '6px',
          border: '2px solid #ef4444',
        }}
      >
        <Text className="text-center font-bold text-red-800 text-xl m-0 mb-2">
          ⚠️ 重要提醒
        </Text>
        <Text className="text-center text-red-700 m-0 mb-4">
          您的獎學金申請草稿尚未送出
        </Text>
        <Text className="text-center font-bold text-red-900 text-2xl m-0">
          剩餘 {days_remaining} 天
        </Text>
      </div>

      <InfoBox>
        <Text className="font-semibold text-gray-900 m-0 mb-2">
          🎓 獎學金類型：{scholarship_type}
        </Text>
        <Text className="text-gray-700 m-0">📅 申請截止日期：{deadline}</Text>
      </InfoBox>

      <Text className="text-gray-700 mb-6">
        申請即將截止！請儘快完成您的申請並送出，逾期將無法受理。
      </Text>

      <div
        className="bg-amber-50 p-4 rounded-md mb-6"
        style={{
          backgroundColor: '#fffbeb',
          padding: '16px',
          borderRadius: '6px',
        }}
      >
        <Text className="text-sm font-semibold text-amber-800 m-0 mb-2">
          📋 送出前檢查清單
        </Text>
        <Text className="text-sm text-amber-700 m-0 mb-1">
          ✓ 個人基本資料已填寫完整
        </Text>
        <Text className="text-sm text-amber-700 m-0 mb-1">
          ✓ 個人陳述已撰寫完成
        </Text>
        <Text className="text-sm text-amber-700 m-0 mb-1">
          ✓ 必要文件已上傳
        </Text>
        <Text className="text-sm text-amber-700 m-0">✓ 資料已檢查無誤</Text>
      </div>

      <div className="mb-6">
        <NYCUButton href={`${system_url}/applications/draft`} text="立即完成申請" />
      </div>

      <Hr className="border-gray-300 my-6" />

      <Text className="text-sm text-gray-600 m-0">
        💡 <strong>溫馨提醒：</strong>
        <br />
        請確保在截止日期前完成送出，系統將於截止時間後自動關閉申請功能。
        <br />
        如有任何問題，請儘快與獎學金辦公室聯繫。
      </Text>
    </BaseTemplate>
  );
}
