import { Img, Section, Text } from '@react-email/components';
import * as React from 'react';

export const Header = () => {
  return (
    <Section className="bg-blue-600 px-8 py-6">
      <Text className="text-white text-2xl font-bold m-0">
        國立陽明交通大學
      </Text>
      <Text className="text-blue-100 text-sm m-0 mt-1">
        National Yang Ming Chiao Tung University
      </Text>
      <Text className="text-white text-base m-0 mt-2">
        獎學金管理系統
      </Text>
    </Section>
  );
};
