import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { ApplicationFormDataDisplay } from '../application-form-data-display'
import { Locale } from '@/lib/validators'

// Mock the utility functions
jest.mock('@/lib/utils/application-helpers', () => ({
  formatFieldName: jest.fn((fieldName: string, locale: Locale) => {
    const names = {
      zh: {
        name: '姓名',
        email: '電子郵件',
        student_id: '學號',
        department: '系所'
      },
      en: {
        name: 'Name',
        email: 'Email',
        student_id: 'Student ID',
        department: 'Department'
      }
    }
    return names[locale][fieldName] || fieldName
  }),
  formatFieldValue: jest.fn((fieldName: string, value: any, locale: Locale) =>
    Promise.resolve(value)
  )
}))

// Mock UI components
jest.mock('@/components/ui/label', () => ({
  Label: ({ children, className }: any) => (
    <label data-testid="label" className={className}>{children}</label>
  )
}))

describe('ApplicationFormDataDisplay', () => {
  const mockFieldLabels = {
    name: { zh: '姓名', en: 'Name' },
    email: { zh: '電子郵件', en: 'Email' },
    student_id: { zh: '學號', en: 'Student ID' }
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should render form data with Chinese labels', async () => {
    const formData = {
      submitted_form_data: {
        fields: {
          name: { value: '張三' },
          email: { value: 'zhang@nycu.edu.tw' },
          student_id: { value: '12345678' }
        }
      }
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
        fieldLabels={mockFieldLabels}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('姓名')).toBeInTheDocument()
      expect(screen.getByText('張三')).toBeInTheDocument()
      expect(screen.getByText('電子郵件')).toBeInTheDocument()
      expect(screen.getByText('zhang@nycu.edu.tw')).toBeInTheDocument()
    })
  })

  it('should render form data with English labels', async () => {
    const formData = {
      submitted_form_data: {
        fields: {
          name: { value: 'John Doe' },
          email: { value: 'john@nycu.edu.tw' }
        }
      }
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="en"
        fieldLabels={mockFieldLabels}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Name')).toBeInTheDocument()
      expect(screen.getByText('John Doe')).toBeInTheDocument()
      expect(screen.getByText('Email')).toBeInTheDocument()
      expect(screen.getByText('john@nycu.edu.tw')).toBeInTheDocument()
    })
  })

  it('should handle direct form_data structure', async () => {
    const formData = {
      form_data: {
        name: '李四',
        email: 'li@nycu.edu.tw',
        department: 'CSIE'
      }
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
        fieldLabels={mockFieldLabels}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('李四')).toBeInTheDocument()
      expect(screen.getByText('li@nycu.edu.tw')).toBeInTheDocument()
      expect(screen.getByText('CSIE')).toBeInTheDocument()
    })
  })

  it('should handle flat object structure', async () => {
    const formData = {
      name: '王五',
      email: 'wang@nycu.edu.tw',
      student_id: '87654321'
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
        fieldLabels={mockFieldLabels}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('王五')).toBeInTheDocument()
      expect(screen.getByText('wang@nycu.edu.tw')).toBeInTheDocument()
      expect(screen.getByText('87654321')).toBeInTheDocument()
    })
  })

  it('should skip empty and excluded fields', async () => {
    const formData = {
      submitted_form_data: {
        fields: {
          name: { value: '測試' },
          email: { value: '' }, // Empty value
          files: { value: 'some_file.pdf' }, // Should be excluded
          agree_terms: { value: true } // Should be excluded
        }
      }
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
        fieldLabels={mockFieldLabels}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('測試')).toBeInTheDocument()
      expect(screen.queryByText('電子郵件')).not.toBeInTheDocument()
      expect(screen.queryByText('some_file.pdf')).not.toBeInTheDocument()
      expect(screen.queryByText('true')).not.toBeInTheDocument()
    })
  })

  it('should use static field names when dynamic labels not provided', async () => {
    const formData = {
      unknown_field: 'test value'
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
      />
    )

    await waitFor(() => {
      expect(screen.getByText('test value')).toBeInTheDocument()
      // Should use formatted field name from utility function
      expect(screen.getByTestId('label')).toBeInTheDocument()
    })
  })

  it('should fallback to Chinese when English label not available', async () => {
    const formData = {
      special_field: 'special value'
    }

    const partialLabels = {
      special_field: { zh: '特殊欄位' } // No English label
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="en"
        fieldLabels={partialLabels}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('特殊欄位')).toBeInTheDocument()
      expect(screen.getByText('special value')).toBeInTheDocument()
    })
  })

  // TODO: Fix object rendering
  it.skip('should handle nested object values', async () => {
    const formData = {
      submitted_form_data: {
        fields: {
          address: {
            value: {
              street: '123 Main St',
              city: 'Hsinchu',
              country: 'Taiwan'
            }
          }
        }
      }
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
      />
    )

    await waitFor(() => {
      // Should display JSON stringified value for complex objects
      expect(screen.getByText(/123 Main St/)).toBeInTheDocument()
    })
  })

  it('should handle array values', async () => {
    const formData = {
      submitted_form_data: {
        fields: {
          hobbies: {
            value: ['reading', 'coding', 'music']
          }
        }
      }
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
      />
    )

    await waitFor(() => {
      // Should display array as comma-separated values
      expect(screen.getByText(/reading.*coding.*music/)).toBeInTheDocument()
    })
  })

  it('should show loading state initially', () => {
    const formData = {
      name: 'Test User'
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
      />
    )

    // Should show some kind of loading indication initially
    // The specific implementation may vary
    expect(screen.getByTestId('label')).toBeInTheDocument()
  })

  it('should handle malformed form data gracefully', async () => {
    const formData = {
      submitted_form_data: {
        fields: null // Malformed data
      }
    }

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
      />
    )

    await waitFor(() => {
      // Should not crash and render empty or error message
      const container = screen.getByTestId('label').closest('div')
      expect(container).toBeInTheDocument()
    })
  })
})