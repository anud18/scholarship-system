import { Hr, Link, Section, Text } from '@react-email/components';
import * as React from 'react';

export const Footer = () => {
  return (
    <>
      <Hr className="border-gray-300 my-6" />
      <Section className="px-8 pb-6">
        <Text className="text-gray-600 text-sm m-0 mb-2">
          國立陽明交通大學 獎學金管理系統
        </Text>
        <Text className="text-gray-500 text-xs m-0 mb-1">
          如有任何問題，請聯繫：scholarship@nycu.edu.tw
        </Text>
        <Text className="text-gray-500 text-xs m-0 mb-2">
          系統網址：
          <Link
            href="https://scholarship.nycu.edu.tw"
            className="text-blue-600 underline"
          >
            https://scholarship.nycu.edu.tw
          </Link>
        </Text>
        <Text className="text-gray-400 text-xs m-0 mt-4">
          此郵件由系統自動發送，請勿直接回覆。
        </Text>
      </Section>
    </>
  );
};
