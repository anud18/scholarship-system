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
        padding: '12px 24px',
        borderRadius: '6px',
        fontWeight: '500',
        textDecoration: 'none',
        display: 'inline-block',
      }}
    >
      {text}
    </Button>
  );
};
