import {
  formatDate,
  getApplicationTimeline,
  getStatusColor,
  getStatusName,
  formatFieldName,
  formatFieldValue,
  getDocumentLabel,
  fetchApplicationFiles,
  ApplicationStatus,
  BadgeVariant
} from '../application-helpers'

// Create mock functions that can be reconfigured
const mockGetAll = jest.fn().mockResolvedValue({
  success: true,
  data: [
    { id: 1, code: 'academic_excellence', name: '學業優秀獎學金', name_en: 'Academic Excellence Scholarship' },
    { id: 2, code: 'research_grant', name: '研究補助', name_en: 'Research Grant' }
  ]
})

const mockGetApplicationById = jest.fn().mockResolvedValue({
  success: true,
  data: {
    id: 1,
    scholarship_type_code: 'academic_excellence',
    status: 'submitted',
    created_at: '2024-01-01',
    updated_at: '2024-01-02',
    documents: [
      {
        id: 'file1',
        filename: 'transcript.pdf',
        file_type: 'transcript'
      }
    ]
  }
})

const mockGetApplicationFiles = jest.fn().mockResolvedValue({
  success: true,
  data: [
    {
      id: 'file1',
      filename: 'test.pdf',
      file_type: 'transcript'
    }
  ]
})

// Mock the API
jest.mock('@/lib/api', () => ({
  api: {
    scholarships: {
      getAll: (...args: any[]) => mockGetAll(...args)
    },
    applications: {
      getApplicationById: (...args: any[]) => mockGetApplicationById(...args),
      getApplicationFiles: (...args: any[]) => mockGetApplicationFiles(...args)
    }
  }
}))

import { api as mockApi } from '@/lib/api'

// Override mockApi with our mock functions so tests can access them
(mockApi.scholarships.getAll as any) = mockGetAll;
(mockApi.applications.getApplicationById as any) = mockGetApplicationById;
(mockApi.applications.getApplicationFiles as any) = mockGetApplicationFiles

describe('Application Helpers', () => {
  describe('formatDate', () => {
    it('should format date for Chinese locale', () => {
      const result = formatDate('2025-01-30T10:00:00Z', 'zh')
      expect(result).toMatch(/2025/) // Should contain year
    })

    it('should format date for English locale', () => {
      const result = formatDate('2025-01-30T10:00:00Z', 'en')
      expect(result).toMatch(/2025/) // Should contain year
    })

    it('should return empty string for null date', () => {
      const result = formatDate(null, 'zh')
      expect(result).toBe('')
    })

    it('should return empty string for undefined date', () => {
      const result = formatDate(undefined, 'zh')
      expect(result).toBe('')
    })

    it('should return empty string for empty date', () => {
      const result = formatDate('', 'zh')
      expect(result).toBe('')
    })
  })

  describe('getApplicationTimeline', () => {
    const mockApplication = {
      status: 'submitted',
      created_at: '2025-01-01T10:00:00Z',
      submitted_at: '2025-01-02T10:00:00Z',
      reviewed_at: '2025-01-03T10:00:00Z',
      approved_at: '2025-01-04T10:00:00Z'
    }

    it('should return correct timeline for draft status in Chinese', () => {
      const draftApp = { ...mockApplication, status: 'draft' }
      const timeline = getApplicationTimeline(draftApp, 'zh')

      expect(timeline).toHaveLength(4)
      expect(timeline[0].title).toBe('提交申請')
      expect(timeline[0].status).toBe('current')
      expect(timeline[1].status).toBe('pending')
      expect(timeline[2].status).toBe('pending')
      expect(timeline[3].status).toBe('pending')
    })

    it('should return correct timeline for submitted status in English', () => {
      const submittedApp = { ...mockApplication, status: 'submitted' }
      const timeline = getApplicationTimeline(submittedApp, 'en')

      expect(timeline).toHaveLength(4)
      expect(timeline[0].title).toBe('Submit Application')
      expect(timeline[0].status).toBe('completed')
      expect(timeline[1].title).toBe('Initial Review')
      expect(timeline[1].status).toBe('current')
    })

    it('should return correct timeline for approved status', () => {
      const approvedApp = { ...mockApplication, status: 'approved' }
      const timeline = getApplicationTimeline(approvedApp, 'zh')

      expect(timeline[0].status).toBe('completed')
      expect(timeline[1].status).toBe('completed')
      expect(timeline[2].status).toBe('completed')
      expect(timeline[3].status).toBe('completed')
    })

    it('should return correct timeline for rejected status', () => {
      const rejectedApp = { ...mockApplication, status: 'rejected' }
      const timeline = getApplicationTimeline(rejectedApp, 'zh')

      expect(timeline[1].status).toBe('rejected')
      expect(timeline[2].status).toBe('rejected')
      expect(timeline[3].status).toBe('rejected')
    })
  })

  describe('getStatusColor', () => {
    it('should return correct colors for different statuses', () => {
      expect(getStatusColor('draft')).toBe('secondary')
      expect(getStatusColor('submitted')).toBe('default')
      expect(getStatusColor('under_review')).toBe('outline')
      expect(getStatusColor('approved')).toBe('default')
      expect(getStatusColor('rejected')).toBe('destructive')
      expect(getStatusColor('withdrawn')).toBe('secondary')
    })
  })

  describe('getStatusName', () => {
    it('should return Chinese status names', () => {
      expect(getStatusName('draft', 'zh')).toBe('草稿')
      expect(getStatusName('submitted', 'zh')).toBe('已提交')
      expect(getStatusName('under_review', 'zh')).toBe('審核中')
      expect(getStatusName('approved', 'zh')).toBe('已核准')
      expect(getStatusName('rejected', 'zh')).toBe('已拒絕')
    })

    it('should return English status names', () => {
      expect(getStatusName('draft', 'en')).toBe('Draft')
      expect(getStatusName('submitted', 'en')).toBe('Submitted')
      expect(getStatusName('under_review', 'en')).toBe('Under Review')
      expect(getStatusName('approved', 'en')).toBe('Approved')
      expect(getStatusName('rejected', 'en')).toBe('Rejected')
    })
  })

  describe('formatFieldName', () => {
    it('should return Chinese field names', () => {
      expect(formatFieldName('academic_year', 'zh')).toBe('學年度')
      expect(formatFieldName('gpa', 'zh')).toBe('學期平均成績')
      expect(formatFieldName('contact_phone', 'zh')).toBe('聯絡電話')
      expect(formatFieldName('bank_account', 'zh')).toBe('銀行帳戶')
    })

    it('should return English field names', () => {
      expect(formatFieldName('academic_year', 'en')).toBe('Academic Year')
      expect(formatFieldName('gpa', 'en')).toBe('GPA')
      expect(formatFieldName('contact_phone', 'en')).toBe('Contact Phone')
      expect(formatFieldName('bank_account', 'en')).toBe('Bank Account')
    })

    it('should return original field name if not mapped', () => {
      expect(formatFieldName('unknown_field', 'zh')).toBe('unknown_field')
      expect(formatFieldName('unknown_field', 'en')).toBe('unknown_field')
    })
  })

  describe('formatFieldValue', () => {
    beforeEach(() => {
      jest.clearAllMocks()
    })

    it('should format scholarship type from API response', async () => {
      mockApi.scholarships.getAll.mockResolvedValue({
        success: true,
        data: [
          { code: 'academic_excellence', name: '學業優秀獎學金', name_en: 'Academic Excellence Scholarship' }
        ]
      })

      const result = await formatFieldValue('scholarship_type', 'academic_excellence', 'zh')
      expect(result).toBe('學業優秀獎學金')

      const resultEn = await formatFieldValue('scholarship_type', 'academic_excellence', 'en')
      expect(resultEn).toBe('Academic Excellence Scholarship')
    })

    it('should return code if scholarship not found in API', async () => {
      mockApi.scholarships.getAll.mockResolvedValue({
        success: true,
        data: []
      })

      const result = await formatFieldValue('scholarship_type', 'unknown_code', 'zh')
      expect(result).toBe('unknown_code')
    })

    it('should return code if API fails', async () => {
      mockApi.scholarships.getAll.mockRejectedValue(new Error('API Error'))

      const result = await formatFieldValue('scholarship_type', 'academic_excellence', 'zh')
      expect(result).toBe('academic_excellence')
    })

    it('should return value as-is for non-scholarship fields', async () => {
      const result = await formatFieldValue('gpa', '3.5', 'zh')
      expect(result).toBe('3.5')
    })
  })

  describe('getDocumentLabel', () => {
    it('should use dynamic label when provided', () => {
      const dynamicLabel = { zh: '動態標籤', en: 'Dynamic Label' }

      expect(getDocumentLabel('transcript', 'zh', dynamicLabel)).toBe('動態標籤')
      expect(getDocumentLabel('transcript', 'en', dynamicLabel)).toBe('Dynamic Label')
    })

    it('should fallback to Chinese label when English not available', () => {
      const dynamicLabel = { zh: '中文標籤' }

      expect(getDocumentLabel('transcript', 'en', dynamicLabel)).toBe('中文標籤')
    })

    it('should use static labels when no dynamic label provided', () => {
      expect(getDocumentLabel('transcript', 'zh')).toBe('成績單')
      expect(getDocumentLabel('transcript', 'en')).toBe('Academic Transcript')
      expect(getDocumentLabel('research_proposal', 'zh')).toBe('研究計畫書')
      expect(getDocumentLabel('cv', 'en')).toBe('CV/Resume')
    })

    it('should return original docType if not mapped', () => {
      expect(getDocumentLabel('unknown_doc', 'zh')).toBe('unknown_doc')
      expect(getDocumentLabel('unknown_doc', 'en')).toBe('unknown_doc')
    })
  })

  describe('fetchApplicationFiles', () => {
    beforeEach(() => {
      jest.clearAllMocks()
    })

    it('should fetch files from application details', async () => {
      const mockDocuments = [
        {
          file_id: 'file1',
          filename: 'transcript.pdf',
          original_filename: 'my_transcript.pdf',
          file_size: 1024,
          mime_type: 'application/pdf',
          document_type: 'transcript',
          file_path: '/files/transcript.pdf',
          download_url: 'http://example.com/download/file1',
          is_verified: true,
          upload_time: '2025-01-01T10:00:00Z'
        }
      ]

      mockApi.applications.getApplicationById.mockResolvedValue({
        success: true,
        data: {
          submitted_form_data: {
            documents: mockDocuments
          }
        }
      })

      const result = await fetchApplicationFiles(1)

      expect(result).toHaveLength(1)
      expect(result[0]).toEqual({
        id: 'file1',
        filename: 'transcript.pdf',
        original_filename: 'my_transcript.pdf',
        file_size: 1024,
        mime_type: 'application/pdf',
        file_type: 'transcript',
        file_path: '/files/transcript.pdf',
        download_url: 'http://example.com/download/file1',
        is_verified: true,
        uploaded_at: '2025-01-01T10:00:00Z'
      })
    })

    it('should fallback to files API if no documents in application details', async () => {
      mockApi.applications.getApplicationById.mockResolvedValue({
        success: true,
        data: {
          submitted_form_data: {}
        }
      })

      const mockFiles = [
        { id: 'file1', filename: 'test.pdf', file_type: 'transcript' }
      ]

      mockApi.applications.getApplicationFiles.mockResolvedValue({
        success: true,
        data: mockFiles
      })

      const result = await fetchApplicationFiles(1)
      expect(result).toEqual(mockFiles)
    })

    it('should return empty array if both APIs fail', async () => {
      mockApi.applications.getApplicationById.mockRejectedValue(new Error('API Error'))
      mockApi.applications.getApplicationFiles.mockRejectedValue(new Error('API Error'))

      const result = await fetchApplicationFiles(1)
      expect(result).toEqual([])
    })

    it('should return empty array if no files found', async () => {
      mockApi.applications.getApplicationById.mockResolvedValue({
        success: true,
        data: { submitted_form_data: {} }
      })

      mockApi.applications.getApplicationFiles.mockResolvedValue({
        success: false,
        data: null
      })

      const result = await fetchApplicationFiles(1)
      expect(result).toEqual([])
    })
  })
})
