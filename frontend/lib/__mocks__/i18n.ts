export const getTranslation = jest.fn((locale: string, key: string) => {
  // Simple mock translations for testing
  const translations: { [locale: string]: { [key: string]: string } } = {
    zh: {
      "gpa.required": "請輸入GPA",
      "gpa.invalid": "GPA必須在0-4之間",
      "ranking.required": "請輸入排名百分比",
      "ranking.invalid": "排名百分比必須在0-100之間",
    },
    en: {
      "gpa.required": "Please enter GPA",
      "gpa.invalid": "GPA must be between 0-4",
      "ranking.required": "Please enter ranking percentage",
      "ranking.invalid": "Ranking percentage must be between 0-100",
    },
  };
  return translations[locale]?.[key] || key;
});
