import {
  Html,
  Head,
  Preview,
  Body,
  Container,
  Tailwind,
} from '@react-email/components';
import * as React from 'react';
import { Header } from './Header';
import { Footer } from './Footer';

interface BaseTemplateProps {
  previewText: string;
  children: React.ReactNode;
}

export const BaseTemplate = ({ previewText, children }: BaseTemplateProps) => {
  return (
    <Html lang="zh-TW">
      <Head />
      <Preview>{previewText}</Preview>
      <Tailwind>
        <Body className="bg-gray-100 font-sans">
          <Container
            className="max-w-[600px] mx-auto bg-white my-8 rounded-lg shadow-lg"
            style={{
              maxWidth: '600px',
              margin: '32px auto',
              backgroundColor: '#ffffff',
              borderRadius: '8px',
              boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
            }}
          >
            <Header />
            <div className="px-8 py-6">{children}</div>
            <Footer />
          </Container>
        </Body>
      </Tailwind>
    </Html>
  );
};
