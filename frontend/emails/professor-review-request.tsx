import { Heading, Text, Hr } from '@react-email/components';
import * as React from 'react';
import { BaseTemplate } from './_components/BaseTemplate';
import { NYCUButton } from './_components/NYCUButton';
import { InfoBox } from './_components/InfoBox';

interface ProfessorReviewRequestProps {
  professor_name?: string;
  student_name?: string;
  app_id?: string;
  scholarship_type?: string;
  submit_date?: string;
  system_url?: string;
}

export default function ProfessorReviewRequest({
  professor_name = '{{professor_name}}',
  student_name = '{{student_name}}',
  app_id = '{{app_id}}',
  scholarship_type = '{{scholarship_type}}',
  submit_date = '{{submit_date}}',
  system_url = '{{system_url}}',
}: ProfessorReviewRequestProps) {
  return (
    <BaseTemplate previewText={`新學生申請待推薦 - ${scholarship_type}`}>
      <Heading className="text-2xl font-bold text-gray-900 mb-4 mt-0">
        新學生申請待推薦
      </Heading>

      <Text className="text-gray-700 mb-4">尊敬的 {professor_name} 教授您好：</Text>

      <Text className="text-gray-700 mb-4">
        您的學生提交了一份獎學金申請，需要您的審核與推薦。
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
        <Text className="text-gray-700 m-0">📅 送出日期：{submit_date}</Text>
      </InfoBox>

      <Text className="text-gray-700 mb-6">
        請您查看該學生的申請資料，並提供您的推薦意見。您的推薦對於學生申請的審核非常重要。
      </Text>

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
          ⏰ 審核提醒
        </Text>
        <Text className="text-sm text-amber-700 m-0">
          請於收到通知後儘快完成審核，以免影響學生申請進度。
        </Text>
      </div>

      <div className="mb-6">
        <NYCUButton
          href={`${system_url}/professor/applications/${app_id}`}
          text="前往審核申請"
        />
      </div>

      <Hr className="border-gray-300 my-6" />

      <Text className="text-sm text-gray-600 m-0">
        💡 <strong>審核流程：</strong>
        <br />
        1. 查看學生申請資料與個人陳述
        <br />
        2. 填寫推薦意見
        <br />
        3. 送出推薦結果
        <br />
        <br />
        如有任何問題，歡迎隨時與各學院系所獎學金承辦人聯繫。
      </Text>
    </BaseTemplate>
  );
}
