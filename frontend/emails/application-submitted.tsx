import { Heading, Text, Hr } from '@react-email/components';
import * as React from 'react';
import { BaseTemplate } from './_components/BaseTemplate';
import { NYCUButton } from './_components/NYCUButton';
import { InfoBox } from './_components/InfoBox';

interface ApplicationSubmittedProps {
  student_name?: string;
  app_id?: string;
  scholarship_type?: string;
  submit_date?: string;
  professor_name?: string;
  system_url?: string;
}

export default function ApplicationSubmitted({
  student_name = '{{student_name}}',
  app_id = '{{app_id}}',
  scholarship_type = '{{scholarship_type}}',
  submit_date = '{{submit_date}}',
  professor_name = '{{professor_name}}',
  system_url = '{{system_url}}',
}: ApplicationSubmittedProps) {
  return (
    <BaseTemplate previewText={`申請已成功送出 - ${scholarship_type}`}>
      <Heading className="text-2xl font-bold text-gray-900 mb-4 mt-0">
        申請已成功送出 ✓
      </Heading>

      <Text className="text-gray-700 mb-4">親愛的 {student_name} 同學您好：</Text>

      <Text className="text-gray-700 mb-4">
        您的獎學金申請已成功送出，以下是您的申請資訊：
      </Text>

      <InfoBox>
        <Text className="font-semibold text-gray-900 m-0 mb-2">
          📋 申請編號：{app_id}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          🎓 獎學金類型：{scholarship_type}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          📅 送出日期：{submit_date}
        </Text>
        <Text className="text-gray-700 m-0">
          👨‍🏫 指導教授：{professor_name}
        </Text>
      </InfoBox>

      <Text className="text-gray-700 mb-6">
        我們將儘快處理您的申請。接下來的審核流程為：
      </Text>

      <div
        className="bg-gray-50 p-4 rounded-md mb-6"
        style={{
          backgroundColor: '#f9fafb',
          padding: '16px',
          borderRadius: '6px',
        }}
      >
        <Text className="text-sm text-gray-700 m-0 mb-2">
          <strong>1. 教授推薦</strong> - 您的指導教授將審核並推薦您的申請
        </Text>
        <Text className="text-sm text-gray-700 m-0 mb-2">
          <strong>2. 學院審查</strong> - 學院將進行審核
        </Text>
        <Text className="text-sm text-gray-700 m-0">
          <strong>3. 結果通知</strong> - 審核完成後將以電子郵件通知您
        </Text>
      </div>

      <Text className="text-gray-700 mb-6">
        您可以隨時透過系統查看申請進度：
      </Text>

      <div className="mb-6">
        <NYCUButton href={`${system_url}/applications/${app_id}`} text="查看申請狀態" />
      </div>

      <Hr className="border-gray-300 my-6" />

      <Text className="text-sm text-gray-600 m-0">
        💡 <strong>溫馨提醒：</strong>
        <br />
        請確保您的聯絡資訊保持最新，以便我們能及時與您聯繫。
        <br />
        如有任何問題，歡迎隨時與各學院系所獎學金承辦人聯繫。
      </Text>
    </BaseTemplate>
  );
}
