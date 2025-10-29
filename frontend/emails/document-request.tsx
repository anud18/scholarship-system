import { Heading, Text, Hr } from '@react-email/components';
import * as React from 'react';
import { BaseTemplate } from './_components/BaseTemplate';
import { NYCUButton } from './_components/NYCUButton';
import { InfoBox } from './_components/InfoBox';

interface DocumentRequestProps {
  student_name?: string;
  app_id?: string;
  scholarship_type?: string;
  requested_documents?: string;
  reason?: string;
  notes?: string;
  requested_by?: string;
  system_url?: string;
}

export default function DocumentRequest({
  student_name = '{{student_name}}',
  app_id = '{{app_id}}',
  scholarship_type = '{{scholarship_type}}',
  requested_documents = '{{requested_documents}}',
  reason = '{{reason}}',
  notes = '{{notes}}',
  requested_by = '{{requested_by}}',
  system_url = '{{system_url}}',
}: DocumentRequestProps) {
  return (
    <BaseTemplate previewText={`文件補件要求 - ${scholarship_type}`}>
      <Heading className="text-2xl font-bold text-gray-900 mb-4 mt-0">
        文件補件要求 📎
      </Heading>

      <Text className="text-gray-700 mb-4">親愛的 {student_name} 同學您好：</Text>

      <Text className="text-gray-700 mb-4">
        您的獎學金申請需要補充下列文件，以便繼續審核作業。
      </Text>

      <InfoBox>
        <Text className="font-semibold text-gray-900 m-0 mb-2">
          📋 申請編號：{app_id}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          🎓 獎學金類型：{scholarship_type}
        </Text>
      </InfoBox>

      <div
        className="bg-red-50 p-4 rounded-md mb-6"
        style={{
          backgroundColor: '#fef2f2',
          padding: '16px',
          borderRadius: '6px',
          borderLeft: '4px solid #ef4444',
        }}
      >
        <Text className="text-sm font-semibold text-red-800 m-0 mb-2">
          📌 需補文件
        </Text>
        <Text className="text-sm text-red-700 m-0 font-medium">
          {requested_documents}
        </Text>
      </div>

      <div
        className="bg-blue-50 p-4 rounded-md mb-6"
        style={{
          backgroundColor: '#eff6ff',
          padding: '16px',
          borderRadius: '6px',
        }}
      >
        <Text className="text-sm font-semibold text-blue-800 m-0 mb-2">
          📝 補件原因
        </Text>
        <Text className="text-sm text-blue-700 m-0">{reason}</Text>
      </div>

      {notes && notes !== '{{notes}}' && (
        <div
          className="bg-gray-50 p-4 rounded-md mb-6"
          style={{
            backgroundColor: '#f9fafb',
            padding: '16px',
            borderRadius: '6px',
          }}
        >
          <Text className="text-sm font-semibold text-gray-800 m-0 mb-2">
            💬 補充說明
          </Text>
          <Text className="text-sm text-gray-700 m-0">{notes}</Text>
        </div>
      )}

      <Text className="text-gray-700 mb-6">
        請儘快登入系統上傳所需文件，以免影響您的申請進度。
      </Text>

      <div className="mb-6">
        <NYCUButton
          href={`${system_url}/applications/${app_id}/documents`}
          text="前往上傳文件"
        />
      </div>

      <Hr className="border-gray-300 my-6" />

      <Text className="text-sm text-gray-600 m-0">
        💡 <strong>上傳提醒：</strong>
        <br />
        • 請確保文件清晰可讀
        <br />
        • 支援 PDF、JPG、PNG 格式
        <br />
        • 單一檔案大小不超過 10MB
        <br />
        <br />
        審核人員：{requested_by}
        <br />
        如有任何問題，歡迎隨時與我們聯繫。
      </Text>
    </BaseTemplate>
  );
}
