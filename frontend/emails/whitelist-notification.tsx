import { Heading, Text, Hr } from '@react-email/components';
import * as React from 'react';
import { BaseTemplate } from './_components/BaseTemplate';
import { NYCUButton } from './_components/NYCUButton';
import { InfoBox } from './_components/InfoBox';

interface WhitelistNotificationProps {
  scholarshipType?: string;
  academicYear?: string;
  semester?: string;
  applicationPeriod?: string;
  deadline?: string;
  eligibilityRequirements?: string;
  systemUrl?: string;
}

export default function WhitelistNotification({
  scholarshipType = '{{scholarshipType}}',
  academicYear = '{{academicYear}}',
  semester = '{{semester}}',
  applicationPeriod = '{{applicationPeriod}}',
  deadline = '{{deadline}}',
  eligibilityRequirements = '{{eligibilityRequirements}}',
  systemUrl = '{{systemUrl}}',
}: WhitelistNotificationProps) {
  return (
    <BaseTemplate
      previewText={`獎學金申請開放通知 - ${scholarshipType} (${academicYear}學年度${semester}學期)`}
    >
      <div
        className="bg-gradient-to-r from-blue-500 to-blue-600 p-6 -mx-8 -mt-6 mb-6 rounded-t-lg"
        style={{
          background: 'linear-gradient(to right, #3b82f6, #2563eb)',
          padding: '24px',
          margin: '-24px -32px 24px -32px',
          borderRadius: '8px 8px 0 0',
        }}
      >
        <Heading className="text-3xl font-bold text-white text-center m-0 mb-2">
          📢 獎學金開放申請
        </Heading>
        <Text className="text-white text-center text-lg m-0">
          您符合申請資格！
        </Text>
      </div>

      <Text className="text-gray-700 mb-4">親愛的同學您好：</Text>

      <Text className="text-gray-700 mb-4">
        根據您的學業表現與資格審核，您符合以下獎學金的申請條件，歡迎提出申請：
      </Text>

      <InfoBox>
        <Text className="font-semibold text-gray-900 m-0 mb-2">
          🎓 獎學金名稱：{scholarshipType}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          📅 學年度：{academicYear} 學年度 {semester}學期
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          🗓️ 申請期間：{applicationPeriod}
        </Text>
        <Text className="font-semibold text-red-700 m-0">
          ⏰ 截止日期：{deadline}
        </Text>
      </InfoBox>

      <div
        className="bg-green-50 p-4 rounded-md mb-6"
        style={{
          backgroundColor: '#f0fdf4',
          padding: '16px',
          borderRadius: '6px',
          borderLeft: '4px solid #22c55e',
        }}
      >
        <Text className="text-sm font-semibold text-green-800 m-0 mb-2">
          ✓ 您符合的申請條件
        </Text>
        <Text className="text-sm text-green-700 m-0">
          {eligibilityRequirements}
        </Text>
      </div>

      <div
        className="bg-amber-50 p-4 rounded-md mb-6"
        style={{
          backgroundColor: '#fffbeb',
          padding: '16px',
          borderRadius: '6px',
        }}
      >
        <Text className="text-sm font-semibold text-amber-800 m-0 mb-2">
          📋 申請流程
        </Text>
        <Text className="text-sm text-amber-700 m-0 mb-1">
          <strong>1.</strong> 登入獎學金系統
        </Text>
        <Text className="text-sm text-amber-700 m-0 mb-1">
          <strong>2.</strong> 填寫申請表單
        </Text>
        <Text className="text-sm text-amber-700 m-0 mb-1">
          <strong>3.</strong> 上傳必要文件
        </Text>
        <Text className="text-sm text-amber-700 m-0 mb-1">
          <strong>4.</strong> 確認資料後送出
        </Text>
        <Text className="text-sm text-amber-700 m-0">
          <strong>5.</strong> 等候審核結果通知
        </Text>
      </div>

      <Text className="text-gray-700 mb-6">
        請把握機會，儘早完成申請。若有任何問題，歡迎隨時與我們聯繫。
      </Text>

      <div className="mb-6">
        <NYCUButton href={`${systemUrl}/scholarships/apply`} text="立即申請" />
      </div>

      <Hr className="border-gray-300 my-6" />

      <Text className="text-sm text-gray-600 m-0">
        💡 <strong>申請提醒：</strong>
        <br />
        • 請於截止日期前完成申請
        <br />
        • 請確保所有資料填寫正確
        <br />
        • 上傳文件需清晰可讀
        <br />
        • 送出前請仔細檢查所有內容
        <br />
        <br />
        祝您申請順利！
      </Text>
    </BaseTemplate>
  );
}
