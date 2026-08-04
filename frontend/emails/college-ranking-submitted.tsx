import { Heading, Text, Hr } from '@react-email/components';
import * as React from 'react';
import { BaseTemplate } from './_components/BaseTemplate';
import { NYCUButton } from './_components/NYCUButton';
import { InfoBox } from './_components/InfoBox';

interface CollegeRankingSubmittedProps {
  college_name?: string;
  ranking_name?: string;
  scholarship_type?: string;
  sub_type_code?: string;
  academic_year?: string;
  semester?: string;
  total_applications?: string;
  finalized_by?: string;
  finalized_at?: string;
  system_url?: string;
}

export default function CollegeRankingSubmitted({
  college_name = '{{college_name}}',
  ranking_name = '{{ranking_name}}',
  scholarship_type = '{{scholarship_type}}',
  sub_type_code = '{{sub_type_code}}',
  academic_year = '{{academic_year}}',
  semester = '{{semester}}',
  total_applications = '{{total_applications}}',
  finalized_by = '{{finalized_by}}',
  finalized_at = '{{finalized_at}}',
  system_url = '{{system_url}}',
}: CollegeRankingSubmittedProps) {
  return (
    <BaseTemplate previewText={`排名已送出 - ${scholarship_type}`}>
      <Heading className="text-2xl font-bold text-gray-900 mb-4 mt-0">
        排名已送出 ✓
      </Heading>

      <Text className="text-gray-700 mb-4">{college_name} 您好：</Text>

      <Text className="text-gray-700 mb-4">
        貴學院的獎學金推薦排名已完成送出並鎖定，後續將由承辦單位進行配額分發。
      </Text>

      <InfoBox>
        <Text className="font-semibold text-gray-900 m-0 mb-2">
          📋 排名名稱：{ranking_name}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          🎓 獎學金類型：{scholarship_type}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          🏷️ 申請類別：{sub_type_code}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          📅 學年度學期：{academic_year} 學年度 {semester}
        </Text>
        <Text className="text-gray-700 m-0 mb-2">
          👥 排名人數：{total_applications}
        </Text>
        <Text className="text-gray-700 m-0">
          🕒 送出時間：{finalized_at}（操作人：{finalized_by}）
        </Text>
      </InfoBox>

      <Text className="text-gray-700 mb-4">
        排名送出後即無法修改。若需調整，請聯繫承辦單位解除鎖定。
      </Text>

      <NYCUButton href={`${system_url}/college/rankings`} text="查看排名" />

      <Hr className="border-gray-200 my-6" />

      <Text className="text-gray-500 text-sm m-0">
        本信件由系統自動發送，請勿直接回覆。
      </Text>
    </BaseTemplate>
  );
}
