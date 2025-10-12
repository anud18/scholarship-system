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
        padding: '16px',
        borderRadius: '6px',
        marginBottom: '24px',
      }}
    >
      {children}
    </Section>
  );
};
