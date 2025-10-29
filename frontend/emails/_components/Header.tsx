import { Img, Section, Text } from '@react-email/components';
import * as React from 'react';

export const Header = () => {
  return (
    <Section
      className="px-8 py-6"
      style={{
        background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
        padding: '28px 32px',
      }}
    >
      <Text
        className="text-white text-2xl font-bold m-0"
        style={{
          color: '#ffffff',
          fontSize: '26px',
          fontWeight: '700',
          margin: '0',
          lineHeight: '1.3',
        }}
      >
        國立陽明交通大學
      </Text>
      <Text
        className="text-blue-100 text-sm m-0 mt-1"
        style={{
          color: '#dbeafe',
          fontSize: '13px',
          margin: '4px 0 0 0',
          lineHeight: '1.4',
          opacity: '0.95',
        }}
      >
        National Yang Ming Chiao Tung University
      </Text>
      <Text
        className="text-white text-base m-0 mt-3"
        style={{
          color: '#ffffff',
          fontSize: '17px',
          fontWeight: '600',
          margin: '12px 0 0 0',
          lineHeight: '1.4',
          letterSpacing: '0.3px',
        }}
      >
        獎學金申請與簽核系統
      </Text>
      <Text
        className="text-blue-100 text-xs m-0 mt-1"
        style={{
          color: '#dbeafe',
          fontSize: '12px',
          margin: '4px 0 0 0',
          lineHeight: '1.4',
          opacity: '0.9',
        }}
      >
        NYCU Admissions Scholarship System
      </Text>
    </Section>
  );
};
