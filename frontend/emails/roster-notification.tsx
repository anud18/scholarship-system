import { Heading, Text, Hr } from '@react-email/components';
import * as React from 'react';
import { BaseTemplate } from './_components/BaseTemplate';
import { NYCUButton } from './_components/NYCUButton';
import { InfoBox } from './_components/InfoBox';

interface RosterNotificationProps {
  studentName?: string;
  scholarshipType?: string;
  academicYear?: string;
  semester?: string;
  approvedAmount?: string;
  rosterNumber?: string;
  followUpItems?: string;
  systemUrl?: string;
}

export default function RosterNotification({
  studentName = '{{studentName}}',
  scholarshipType = '{{scholarshipType}}',
  academicYear = '{{academicYear}}',
  semester = '{{semester}}',
  approvedAmount = '{{approvedAmount}}',
  rosterNumber = '{{rosterNumber}}',
  followUpItems = '{{followUpItems}}',
  systemUrl = '{{systemUrl}}',
}: RosterNotificationProps) {
  return (
    <BaseTemplate
      previewText={`獲獎名冊確認通知 - ${scholarshipType} (${academicYear}學年度${semester}學期)`}
    >
      <div
        className="bg-gradient-to-r from-yellow-400 to-yellow-500 p-6 -mx-8 -mt-6 mb-6 rounded-t-lg"
        style={{
          background: 'linear-gradient(to right, #fbbf24, #f59e0b)',
          padding: '24px',
          margin: '-24px -32px 24px -32px',
          borderRadius: '8px 8px 0 0',
        }}
      >
        <Heading className="text-3xl font-bold text-white text-center m-0 mb-2">
          🎊 恭喜您！🎊
        </Heading>
        <Text className="text-white text-center text-xl font-semibold m-0">
          您已獲得獎學金
        </Text>
      </div>

      <Text className="text-gray-700 mb-4">親愛的 {studentName} 同學您好：</Text>

      <Text className="text-gray-700 mb-4">
        恭喜您！您已列入本學期獎學金獲獎名冊，詳細資訊如下：
      </Text>

      <InfoBox>
        <Text className="font-semibold text-gray-900 m-0 mb-2">
          🎓 獎學金名稱：{scholarshipType}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          📅 學年度：{academicYear} 學年度 {semester}學期
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          📋 名冊編號：{rosterNumber}
        </Text>
        <Text className="font-bold text-green-700 text-xl m-0 mt-3">
          💰 獎學金金額：{approvedAmount}
        </Text>
      </InfoBox>

      <div
        className="bg-blue-50 p-4 rounded-md mb-6"
        style={{
          backgroundColor: '#eff6ff',
          padding: '16px',
          borderRadius: '6px',
        }}
      >
        <Text className="text-sm font-semibold text-blue-800 m-0 mb-2">
          💳 撥款資訊
        </Text>
        <Text className="text-sm text-blue-700 m-0">
          獎學金將於作業完成後直接匯入您的銀行帳戶。
          <br />
          請確認您在系統中的銀行帳戶資料正確無誤。
        </Text>
      </div>

      {followUpItems && followUpItems !== '{{followUpItems}}' && (
        <div
          className="bg-amber-50 p-4 rounded-md mb-6"
          style={{
            backgroundColor: '#fffbeb',
            padding: '16px',
            borderRadius: '6px',
            borderLeft: '4px solid #f59e0b',
          }}
        >
          <Text className="text-sm font-semibold text-amber-800 m-0 mb-2">
            📌 後續配合事項
          </Text>
          <Text className="text-sm text-amber-700 m-0">{followUpItems}</Text>
        </div>
      )}

      <div className="mb-6">
        <NYCUButton href={`${systemUrl}/profile/bank-info`} text="確認銀行帳戶資料" />
      </div>

      <Hr className="border-gray-300 my-6" />

      <Text className="text-sm text-gray-600 m-0">
        💡 <strong>注意事項：</strong>
        <br />
        • 請務必確認銀行帳戶資料正確
        <br />
        • 如有變更，請儘速至系統更新
        <br />
        • 撥款時間將另行通知
        <br />
        • 如有任何問題，請與獎學金辦公室聯繫
        <br />
        <br />
        再次恭喜您獲得此項殊榮！
      </Text>
    </BaseTemplate>
  );
}
