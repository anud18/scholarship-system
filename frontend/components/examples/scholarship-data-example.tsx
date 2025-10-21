'use client';

/**
 * Example component demonstrating useScholarshipData hook usage
 *
 * Shows various patterns for using the hook in real applications
 */

import React from 'react';
import { useScholarshipData, getScholarshipName, getSubTypeName } from '@/hooks/use-scholarship-data';
import { useLanguagePreference } from '@/hooks/use-language-preference';

/**
 * Example 1: Simple scholarship list display
 */
export function ScholarshipListExample() {
  const { scholarships, isLoading, error, refresh } = useScholarshipData(true);

  if (isLoading) {
    return <div className="p-4 text-gray-600">載入獎學金列表中...</div>;
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded">
        <p className="text-red-700">無法載入獎學金資料</p>
        <button
          onClick={() => refresh()}
          className="mt-2 px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700"
        >
          重試
        </button>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-bold mb-4">可用的獎學金</h2>
      <ul className="space-y-2">
        {scholarships.map(scholarship => (
          <li key={scholarship.id} className="p-2 border rounded hover:bg-gray-50">
            <div className="font-semibold">{scholarship.name}</div>
            <div className="text-sm text-gray-600">{scholarship.name_en || 'N/A'}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Example 2: Scholarship display with locale support
 */
export function ScholarshipWithLocaleExample() {
  const { locale } = useLanguagePreference("student");
  const { scholarships, isLoading } = useScholarshipData(true);

  if (isLoading) {
    return <div className="p-4">Loading...</div>;
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-bold mb-4">
        {locale === 'zh' ? '獎學金列表' : 'Scholarship List'}
      </h2>
      <table className="w-full border-collapse border border-gray-300">
        <thead className="bg-gray-100">
          <tr>
            <th className="border p-2 text-left">
              {locale === 'zh' ? '代碼' : 'Code'}
            </th>
            <th className="border p-2 text-left">
              {locale === 'zh' ? '名稱' : 'Name'}
            </th>
            <th className="border p-2 text-left">
              {locale === 'zh' ? '狀態' : 'Status'}
            </th>
          </tr>
        </thead>
        <tbody>
          {scholarships.map(scholarship => (
            <tr key={scholarship.id} className="hover:bg-gray-50">
              <td className="border p-2">{scholarship.code}</td>
              <td className="border p-2">
                {locale === 'zh' ? scholarship.name : scholarship.name_en || scholarship.name}
              </td>
              <td className="border p-2">{scholarship.status || 'Active'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Example 3: Sub-type translation display
 */
export function SubTypeTranslationExample() {
  const { locale } = useLanguagePreference("student");
  const { subTypeTranslations, isLoading, getSubTypeName } = useScholarshipData(true);

  if (isLoading) {
    return <div className="p-4">Loading...</div>;
  }

  const exampleCodes = ['domestic', 'overseas', 'international'];

  return (
    <div className="p-4">
      <h2 className="text-lg font-bold mb-4">
        {locale === 'zh' ? '學生類別翻譯' : 'Sub-Type Translations'}
      </h2>
      <div className="grid grid-cols-2 gap-4">
        {exampleCodes.map(code => (
          <div key={code} className="p-3 border rounded">
            <div className="text-sm text-gray-600">Code: {code}</div>
            <div className="font-semibold">
              {locale === 'zh'
                ? getSubTypeName(code, 'zh')
                : getSubTypeName(code, 'en')}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Example 4: Application card showing scholarship info
 */
interface ApplicationCardProps {
  applicationId: number;
  scholarshipId: number;
  subType: string;
}

export function ApplicationCardExample({ applicationId, scholarshipId, subType }: ApplicationCardProps) {
  const { locale } = useLanguagePreference("student");
  const {
    getScholarshipName,
    getSubTypeName,
    subTypeTranslations,
    isLoading,
  } = useScholarshipData(true);

  if (isLoading) {
    return <div className="p-4 bg-gray-100 rounded h-24" />;
  }

  return (
    <div className="p-4 border rounded-lg shadow hover:shadow-md transition">
      <div className="mb-2">
        <span className="text-xs font-semibold text-gray-600 uppercase">
          {locale === 'zh' ? '應用編號' : 'Application ID'}
        </span>
        <div className="font-mono text-sm">{applicationId}</div>
      </div>

      <div className="mb-2">
        <span className="text-xs font-semibold text-gray-600 uppercase">
          {locale === 'zh' ? '獎學金' : 'Scholarship'}
        </span>
        <div className="font-semibold">
          {getScholarshipName(scholarshipId, locale === 'zh' ? 'zh' : 'en')}
        </div>
      </div>

      <div>
        <span className="text-xs font-semibold text-gray-600 uppercase">
          {locale === 'zh' ? '學生類別' : 'Sub-Type'}
        </span>
        <div className="font-semibold">
          {getSubTypeName(subType, locale === 'zh' ? 'zh' : 'en')}
        </div>
      </div>
    </div>
  );
}

/**
 * Example 5: Scholarship selector dropdown
 */
interface ScholarshipSelectorProps {
  value?: number;
  onChange: (scholarshipId: number) => void;
}

export function ScholarshipSelectorExample({ value, onChange }: ScholarshipSelectorProps) {
  const { locale } = useLanguagePreference("student");
  const { scholarships, isLoading } = useScholarshipData(true);

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {locale === 'zh' ? '選擇獎學金' : 'Select Scholarship'}
      </label>
      <select
        value={value || ''}
        onChange={e => onChange(parseInt(e.target.value))}
        disabled={isLoading}
        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        <option value="">
          {isLoading
            ? locale === 'zh' ? '載入中...' : 'Loading...'
            : locale === 'zh' ? '-- 選擇獎學金 --' : '-- Select Scholarship --'}
        </option>
        {scholarships.map(scholarship => (
          <option key={scholarship.id} value={scholarship.id}>
            {scholarship.name}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Example 6: Scholarship data with manual refresh
 */
export function ScholarshipAdminPanelExample() {
  const { locale } = useLanguagePreference("student");
  const { scholarships, isLoading, refresh } = useScholarshipData(true);
  const [isRefreshing, setIsRefreshing] = React.useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await refresh();
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="p-6 bg-white rounded-lg border">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-bold">
          {locale === 'zh' ? '獎學金管理' : 'Scholarship Management'}
        </h3>
        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
        >
          {isRefreshing ? '重新整理中...' : locale === 'zh' ? '重新整理' : 'Refresh'}
        </button>
      </div>

      {isLoading ? (
        <div className="text-gray-600">{locale === 'zh' ? '載入中...' : 'Loading...'}</div>
      ) : (
        <div className="space-y-2">
          {scholarships.map(scholarship => (
            <div key={scholarship.id} className="p-3 border rounded hover:bg-gray-50">
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-semibold">{scholarship.name}</div>
                  <div className="text-sm text-gray-600">{scholarship.code}</div>
                </div>
                <span className={`px-2 py-1 text-xs rounded ${
                  scholarship.status === 'active'
                    ? 'bg-green-100 text-green-800'
                    : 'bg-gray-100 text-gray-800'
                }`}>
                  {scholarship.status || 'Active'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Main example component showcasing all patterns
 */
export function ScholarshipDataExamples() {
  return (
    <div className="space-y-8 p-4">
      <section>
        <h2 className="text-2xl font-bold mb-4">Example 1: Basic List</h2>
        <ScholarshipListExample />
      </section>

      <section>
        <h2 className="text-2xl font-bold mb-4">Example 2: With Locale Support</h2>
        <ScholarshipWithLocaleExample />
      </section>

      <section>
        <h2 className="text-2xl font-bold mb-4">Example 3: Sub-Type Translations</h2>
        <SubTypeTranslationExample />
      </section>

      <section>
        <h2 className="text-2xl font-bold mb-4">Example 4: Application Card</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ApplicationCardExample applicationId={1} scholarshipId={1} subType="domestic" />
          <ApplicationCardExample applicationId={2} scholarshipId={2} subType="overseas" />
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-bold mb-4">Example 5: Selector</h2>
        <div className="max-w-sm">
          <ScholarshipSelectorExample onChange={id => console.log('Selected:', id)} />
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-bold mb-4">Example 6: Admin Panel</h2>
        <ScholarshipAdminPanelExample />
      </section>
    </div>
  );
}
