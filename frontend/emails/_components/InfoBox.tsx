import { Section, Text } from '@react-email/components';
import * as React from 'react';

interface InfoBoxProps {
  children: React.ReactNode;
}

export const InfoBox = ({ children }: InfoBoxProps) => {
  return (
    <Section
      className="bg-blue-50 p-4 rounded-md mb-6"
      style={{
        backgroundColor: '#eff6ff',
        padding: '20px',
        borderRadius: '8px',
        marginBottom: '24px',
        borderLeft: '4px solid #2563eb',
        boxShadow: '0 1px 3px rgba(37, 99, 235, 0.08)',
      }}
    >
      {children}
    </Section>
  );
};
