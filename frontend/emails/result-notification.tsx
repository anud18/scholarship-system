import { Heading, Text, Hr } from '@react-email/components';
import * as React from 'react';
import { BaseTemplate } from './_components/BaseTemplate';
import { NYCUButton } from './_components/NYCUButton';
import { InfoBox } from './_components/InfoBox';

interface ResultNotificationProps {
  student_name?: string;
  app_id?: string;
  scholarship_type?: string;
  result_status?: string;
  approved_amount?: string;
  result_message?: string;
  next_steps?: string;
  system_url?: string;
}

export default function ResultNotification({
  student_name = '{{student_name}}',
  app_id = '{{app_id}}',
  scholarship_type = '{{scholarship_type}}',
  result_status = '{{result_status}}',
  approved_amount = '{{approved_amount}}',
  result_message = '{{result_message}}',
  next_steps = '{{next_steps}}',
  system_url = '{{system_url}}',
}: ResultNotificationProps) {
  const isApproved = result_status.includes('核准') || result_status.includes('通過');

  return (
    <BaseTemplate previewText={`獎學金審核結果通知 - ${scholarship_type}`}>
      <Heading className="text-2xl font-bold text-gray-900 mb-4 mt-0">
        獎學金審核結果通知
      </Heading>

      <Text className="text-gray-700 mb-4">親愛的 {student_name} 同學您好：</Text>

      <Text className="text-gray-700 mb-4">
        您的獎學金申請審核已完成，結果如下：
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
        className={`p-6 rounded-md mb-6 ${isApproved ? 'bg-green-50' : 'bg-gray-50'}`}
        style={{
          backgroundColor: isApproved ? '#f0fdf4' : '#f9fafb',
          padding: '24px',
          borderRadius: '6px',
          border: `2px solid ${isApproved ? '#22c55e' : '#9ca3af'}`,
        }}
      >
        <Text className="text-center font-bold text-xl m-0 mb-3" style={{ color: isApproved ? '#15803d' : '#4b5563' }}>
          {isApproved ? '🎉 恭喜您！' : '審核結果'}
        </Text>
        <Text className="text-center font-semibold text-2xl m-0 mb-2" style={{ color: isApproved ? '#15803d' : '#4b5563' }}>
          {result_status}
        </Text>
        {isApproved && approved_amount && approved_amount !== '{{approved_amount}}' && (
          <Text className="text-center font-bold text-3xl m-0" style={{ color: '#15803d' }}>
            {approved_amount}
          </Text>
        )}
      </div>

      {result_message && result_message !== '{{result_message}}' && (
        <div
          className="bg-blue-50 p-4 rounded-md mb-6"
          style={{
            backgroundColor: '#eff6ff',
            padding: '16px',
            borderRadius: '6px',
          }}
        >
          <Text className="text-sm font-semibold text-blue-800 m-0 mb-2">
            📝 審核意見
          </Text>
          <Text className="text-sm text-blue-700 m-0">{result_message}</Text>
        </div>
      )}

      {next_steps && next_steps !== '{{next_steps}}' && (
        <div
          className="bg-amber-50 p-4 rounded-md mb-6"
          style={{
            backgroundColor: '#fffbeb',
            padding: '16px',
            borderRadius: '6px',
          }}
        >
          <Text className="text-sm font-semibold text-amber-800 m-0 mb-2">
            📌 後續事項
          </Text>
          <Text className="text-sm text-amber-700 m-0">{next_steps}</Text>
        </div>
      )}

      <div className="mb-6">
        <NYCUButton href={`${system_url}/applications/${app_id}`} text="查看詳細結果" />
      </div>

      <Hr className="border-gray-300 my-6" />

      <Text className="text-sm text-gray-600 m-0">
        {isApproved ? (
          <>
            💡 <strong>恭喜您獲得獎學金！</strong>
            <br />
            後續撥款事宜將另行通知，請保持聯絡資訊暢通。
            <br />
            如有任何問題，歡迎隨時與我們聯繫。
          </>
        ) : (
          <>
            💡 <strong>感謝您的申請</strong>
            <br />
            雖然本次申請未能通過，我們鼓勵您繼續努力。
            <br />
            歡迎您關注其他獎學金機會，或在下一學期再次申請。
          </>
        )}
      </Text>
    </BaseTemplate>
  );
}
