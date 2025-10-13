import { Heading, Text, Hr } from '@react-email/components';
import * as React from 'react';
import { BaseTemplate } from './_components/BaseTemplate';
import { NYCUButton } from './_components/NYCUButton';
import { InfoBox } from './_components/InfoBox';

interface CollegeReviewRequestProps {
  college_name?: string;
  student_name?: string;
  app_id?: string;
  scholarship_type?: string;
  professor_name?: string;
  submit_date?: string;
  professor_recommendation?: string;
  review_deadline?: string;
  system_url?: string;
}

export default function CollegeReviewRequest({
  college_name = '{{college_name}}',
  student_name = '{{student_name}}',
  app_id = '{{app_id}}',
  scholarship_type = '{{scholarship_type}}',
  professor_name = '{{professor_name}}',
  submit_date = '{{submit_date}}',
  professor_recommendation = '{{professor_recommendation}}',
  review_deadline = '{{review_deadline}}',
  system_url = '{{system_url}}',
}: CollegeReviewRequestProps) {
  return (
    <BaseTemplate previewText={`新申請案待審核 - ${scholarship_type}`}>
      <Heading className="text-2xl font-bold text-gray-900 mb-4 mt-0">
        新申請案待審核
      </Heading>

      <Text className="text-gray-700 mb-4">{college_name} 您好：</Text>

      <Text className="text-gray-700 mb-4">
        有一份獎學金申請已由教授推薦，需要貴學院進行審核。
      </Text>

      <InfoBox>
        <Text className="font-semibold text-gray-900 m-0 mb-2">
          📋 申請編號：{app_id}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          👨‍🎓 學生姓名：{student_name}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          🎓 獎學金類型：{scholarship_type}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          👨‍🏫 推薦教授：{professor_name}
        </Text>
        <Text className="text-gray-700 m-0">📅 送出日期：{submit_date}</Text>
      </InfoBox>

      {professor_recommendation && professor_recommendation !== '{{professor_recommendation}}' && (
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
            ✓ 教授推薦意見
          </Text>
          <Text className="text-sm text-green-700 m-0 italic">
            {professor_recommendation}
          </Text>
        </div>
      )}

      {review_deadline && review_deadline !== '{{review_deadline}}' && (
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
            ⏰ 審核期限
          </Text>
          <Text className="text-sm text-amber-700 m-0">
            請於 {review_deadline} 前完成審核
          </Text>
        </div>
      )}

      <Text className="text-gray-700 mb-6">
        請登入系統查看完整申請資料，並完成學院審核作業。
      </Text>

      <div className="mb-6">
        <NYCUButton
          href={`${system_url}/college/applications/${app_id}`}
          text="前往審核系統"
        />
      </div>

      <Hr className="border-gray-300 my-6" />

      <Text className="text-sm text-gray-600 m-0">
        💡 <strong>審核事項：</strong>
        <br />
        • 學生基本資料與學業成績
        <br />
        • 教授推薦意見
        <br />
        • 申請資格與條件符合性
        <br />
        • 其他相關證明文件
        <br />
        <br />
        如有任何問題，請與獎學金辦公室聯繫。
      </Text>
    </BaseTemplate>
  );
}
