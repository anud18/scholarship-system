import { Button } from '@react-email/components';
import * as React from 'react';

interface NYCUButtonProps {
  href: string;
  text: string;
}

export const NYCUButton = ({ href, text }: NYCUButtonProps) => {
  return (
    <Button
      href={href}
      className="bg-blue-600 text-white px-6 py-3 rounded-md font-medium inline-block no-underline text-center"
      style={{
        backgroundColor: '#2563eb',
        color: '#ffffff',
        padding: '14px 32px',
        borderRadius: '8px',
        fontWeight: '600',
        fontSize: '15px',
        textDecoration: 'none',
        display: 'inline-block',
        textAlign: 'center',
        minHeight: '44px',
        minWidth: '120px',
        lineHeight: '1.5',
        boxShadow: '0 2px 8px rgba(37, 99, 235, 0.25)',
        transition: 'all 0.2s ease',
        border: 'none',
        cursor: 'pointer',
      }}
    >
      {text}
    </Button>
  );
};
