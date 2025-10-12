import { Heading, Text, Hr } from '@react-email/components';
import * as React from 'react';
import { BaseTemplate } from './_components/BaseTemplate';
import { NYCUButton } from './_components/NYCUButton';
import { InfoBox } from './_components/InfoBox';

interface CollegeReviewRequestProps {
  collegeName?: string;
  studentName?: string;
  appId?: string;
  scholarshipType?: string;
  professorName?: string;
  submitDate?: string;
  professorRecommendation?: string;
  reviewDeadline?: string;
  systemUrl?: string;
}

export default function CollegeReviewRequest({
  collegeName = '{{collegeName}}',
  studentName = '{{studentName}}',
  appId = '{{appId}}',
  scholarshipType = '{{scholarshipType}}',
  professorName = '{{professorName}}',
  submitDate = '{{submitDate}}',
  professorRecommendation = '{{professorRecommendation}}',
  reviewDeadline = '{{reviewDeadline}}',
  systemUrl = '{{systemUrl}}',
}: CollegeReviewRequestProps) {
  return (
    <BaseTemplate previewText={`新申請案待審核 - ${scholarshipType}`}>
      <Heading className="text-2xl font-bold text-gray-900 mb-4 mt-0">
        新申請案待審核
      </Heading>

      <Text className="text-gray-700 mb-4">{collegeName} 您好：</Text>

      <Text className="text-gray-700 mb-4">
        有一份獎學金申請已由教授推薦，需要貴學院進行審核。
      </Text>

      <InfoBox>
        <Text className="font-semibold text-gray-900 m-0 mb-2">
          📋 申請編號：{appId}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          👨‍🎓 學生姓名：{studentName}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          🎓 獎學金類型：{scholarshipType}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          👨‍🏫 推薦教授：{professorName}
        </Text>
        <Text className="text-gray-700 m-0">📅 送出日期：{submitDate}</Text>
      </InfoBox>

      {professorRecommendation && professorRecommendation !== '{{professorRecommendation}}' && (
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
            {professorRecommendation}
          </Text>
        </div>
      )}

      {reviewDeadline && reviewDeadline !== '{{reviewDeadline}}' && (
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
            請於 {reviewDeadline} 前完成審核
          </Text>
        </div>
      )}

      <Text className="text-gray-700 mb-6">
        請登入系統查看完整申請資料，並完成學院審核作業。
      </Text>

      <div className="mb-6">
        <NYCUButton
          href={`${systemUrl}/college/applications/${appId}`}
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
