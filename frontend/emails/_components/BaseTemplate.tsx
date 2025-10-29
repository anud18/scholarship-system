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
        <Body
          className="bg-gray-100 font-sans"
          style={{
            backgroundColor: '#f9fafb',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
            margin: '0',
            padding: '0',
          }}
        >
          <Container
            className="max-w-[600px] mx-auto bg-white my-8 rounded-lg shadow-lg"
            style={{
              maxWidth: '600px',
              margin: '32px auto',
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.08), 0 2px 4px rgba(0, 0, 0, 0.04)',
              overflow: 'hidden',
            }}
          >
            <Header />
            <div
              className="px-8 py-6"
              style={{
                padding: '28px 32px',
              }}
            >
              {children}
            </div>
            <Footer />
          </Container>
        </Body>
      </Tailwind>
    </Html>
  );
};
