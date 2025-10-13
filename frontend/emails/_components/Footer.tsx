import { Hr, Link, Section, Text } from '@react-email/components';
import * as React from 'react';

export const Footer = () => {
  return (
    <>
      <Hr
        className="border-gray-300 my-6"
        style={{
          borderColor: '#e5e7eb',
          borderTop: '1px solid #e5e7eb',
          margin: '24px 0',
        }}
      />
      <Section
        className="px-8 pb-6"
        style={{
          padding: '0 32px 28px 32px',
        }}
      >
        <Text
          className="text-gray-700 text-sm font-semibold m-0 mb-3"
          style={{
            color: '#374151',
            fontSize: '14px',
            fontWeight: '600',
            margin: '0 0 12px 0',
            lineHeight: '1.5',
          }}
        >
          國立陽明交通大學 獎學金申請與簽核系統
        </Text>
        <Text
          className="text-gray-600 text-xs m-0 mb-2"
          style={{
            color: '#6b7280',
            fontSize: '13px',
            margin: '0 0 8px 0',
            lineHeight: '1.6',
          }}
        >
          <strong style={{ fontWeight: '600' }}>聯絡我們：</strong> scholarship@nycu.edu.tw
        </Text>
        <Text
          className="text-gray-600 text-xs m-0 mb-3"
          style={{
            color: '#6b7280',
            fontSize: '13px',
            margin: '0 0 12px 0',
            lineHeight: '1.6',
          }}
        >
          <strong style={{ fontWeight: '600' }}>系統網址：</strong>
          <Link
            href="https://scholarship.nycu.edu.tw"
            className="text-blue-600 underline"
            style={{
              color: '#2563eb',
              textDecoration: 'underline',
              marginLeft: '4px',
            }}
          >
            scholarship.nycu.edu.tw
          </Link>
        </Text>
        <Hr
          className="border-gray-200 my-3"
          style={{
            borderColor: '#f3f4f6',
            borderTop: '1px solid #f3f4f6',
            margin: '12px 0',
          }}
        />
        <Text
          className="text-gray-400 text-xs m-0"
          style={{
            color: '#9ca3af',
            fontSize: '11px',
            margin: '0',
            lineHeight: '1.5',
            fontStyle: 'italic',
          }}
        >
          此郵件由系統自動發送，請勿直接回覆。如有問題請透過上述聯絡方式與我們聯繫。
        </Text>
      </Section>
    </>
  );
};
