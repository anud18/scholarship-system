import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FileUpload } from '../file-upload'

// Mock the API
jest.mock('@/lib/api', () => ({
  api: {
    files: {
      upload: jest.fn().mockResolvedValue({
        success: true,
        data: {
          file_id: 'test-file-123',
          filename: 'test.pdf',
          file_url: '/uploads/test.pdf'
        }
      }),
      delete: jest.fn().mockResolvedValue({
        success: true,
        data: { message: 'File deleted successfully' }
      })
    }
  }
}))

// Mock Lucide icons
jest.mock('lucide-react', () => ({
  Upload: () => <div data-testid="upload-icon">Upload</div>,
  X: () => <div data-testid="x-icon">X</div>,
  File: () => <div data-testid="file-icon">File</div>,
  Image: () => <div data-testid="image-icon">Image</div>
}))

const mockApi = require('@/lib/api').api

describe('FileUpload Component', () => {
  const defaultProps = {
    onFilesChange: jest.fn(),
    acceptedTypes: '.pdf,.doc,.docx',
    maxSize: 5 * 1024 * 1024, // 5MB
    maxFiles: 3
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should render upload area correctly', () => {
    render(<FileUpload {...defaultProps} />)

    expect(screen.getByText(/drag.*drop.*files/i)).toBeInTheDocument()
    expect(screen.getByText(/click.*browse/i)).toBeInTheDocument()
    expect(screen.getByTestId('upload-icon')).toBeInTheDocument()
  })

  it('should handle file selection via input', async () => {
    const user = userEvent.setup()
    render(<FileUpload {...defaultProps} />)

    const file = new File(['test content'], 'test.pdf', { type: 'application/pdf' })
    const input = screen.getByRole('button', { name: /browse/i }).querySelector('input[type="file"]') ||
                  document.querySelector('input[type="file"]')

    if (input) {
      await user.upload(input as HTMLInputElement, file)

      await waitFor(() => {
        expect(mockApi.files.upload).toHaveBeenCalledWith(
          expect.objectContaining({
            get: expect.any(Function)
          })
        )
      })
    }
  })

  it('should reject files that exceed size limit', async () => {
    const user = userEvent.setup()
    render(<FileUpload {...defaultProps} />)

    // Create a large file (6MB > 5MB limit)
    const largeFile = new File(['x'.repeat(6 * 1024 * 1024)], 'large.pdf', {
      type: 'application/pdf'
    })

    const input = document.querySelector('input[type="file"]')
    if (input) {
      await user.upload(input as HTMLInputElement, largeFile)

      await waitFor(() => {
        expect(screen.getByText(/file.*too.*large/i)).toBeInTheDocument()
      })
    }
  })

  it('should reject files with invalid types', async () => {
    const user = userEvent.setup()
    render(<FileUpload {...defaultProps} />)

    const invalidFile = new File(['test'], 'test.txt', { type: 'text/plain' })

    const input = document.querySelector('input[type="file"]')
    if (input) {
      await user.upload(input as HTMLInputElement, invalidFile)

      await waitFor(() => {
        expect(screen.getByText(/invalid.*file.*type/i)).toBeInTheDocument()
      })
    }
  })

  it('should enforce maximum file count limit', async () => {
    const user = userEvent.setup()
    render(<FileUpload {...defaultProps} maxFiles={1} />)

    const file1 = new File(['content1'], 'file1.pdf', { type: 'application/pdf' })
    const file2 = new File(['content2'], 'file2.pdf', { type: 'application/pdf' })

    const input = document.querySelector('input[type="file"]')
    if (input) {
      // Upload first file
      await user.upload(input as HTMLInputElement, file1)

      await waitFor(() => {
        expect(mockApi.files.upload).toHaveBeenCalledTimes(1)
      })

      // Try to upload second file
      await user.upload(input as HTMLInputElement, file2)

      await waitFor(() => {
        expect(screen.getByText(/maximum.*file.*limit/i)).toBeInTheDocument()
      })
    }
  })

  it('should handle drag and drop events', async () => {
    render(<FileUpload {...defaultProps} />)

    const dropzone = screen.getByText(/drag.*drop.*files/i).closest('div')
    const file = new File(['test content'], 'test.pdf', { type: 'application/pdf' })

    if (dropzone) {
      // Simulate drag over
      fireEvent.dragOver(dropzone, {
        dataTransfer: {
          files: [file],
          types: ['Files']
        }
      })

      expect(dropzone).toHaveClass(/border-primary/i)

      // Simulate drop
      fireEvent.drop(dropzone, {
        dataTransfer: {
          files: [file],
          types: ['Files']
        }
      })

      await waitFor(() => {
        expect(mockApi.files.upload).toHaveBeenCalled()
      })
    }
  })

  it('should show file upload progress', async () => {
    // Mock upload with delay to show progress
    mockApi.files.upload.mockImplementation(() =>
      new Promise(resolve => {
        setTimeout(() => resolve({
          success: true,
          data: { file_id: 'test-123', filename: 'test.pdf' }
        }), 100)
      })
    )

    const user = userEvent.setup()
    render(<FileUpload {...defaultProps} />)

    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]')

    if (input) {
      await user.upload(input as HTMLInputElement, file)

      // Should show uploading state
      expect(screen.getByText(/uploading/i)).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.queryByText(/uploading/i)).not.toBeInTheDocument()
      })
    }
  })

  it('should allow file removal', async () => {
    const user = userEvent.setup()
    render(<FileUpload {...defaultProps} />)

    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]')

    if (input) {
      await user.upload(input as HTMLInputElement, file)

      await waitFor(() => {
        expect(screen.getByText('test.pdf')).toBeInTheDocument()
      })

      const removeButton = screen.getByTestId('x-icon').closest('button')
      if (removeButton) {
        await user.click(removeButton)

        await waitFor(() => {
          expect(mockApi.files.delete).toHaveBeenCalled()
          expect(defaultProps.onFilesChange).toHaveBeenCalledWith([])
        })
      }
    }
  })

  it('should handle upload errors gracefully', async () => {
    mockApi.files.upload.mockRejectedValue(new Error('Upload failed'))

    const user = userEvent.setup()
    render(<FileUpload {...defaultProps} />)

    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]')

    if (input) {
      await user.upload(input as HTMLInputElement, file)

      await waitFor(() => {
        expect(screen.getByText(/upload.*failed/i)).toBeInTheDocument()
      })
    }
  })

  it('should call onFilesChange when files are added', async () => {
    const user = userEvent.setup()
    render(<FileUpload {...defaultProps} />)

    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]')

    if (input) {
      await user.upload(input as HTMLInputElement, file)

      await waitFor(() => {
        expect(defaultProps.onFilesChange).toHaveBeenCalledWith(
          expect.arrayContaining([
            expect.objectContaining({
              filename: 'test.pdf',
              file_id: 'test-file-123'
            })
          ])
        )
      })
    }
  })

  it('should show file preview for images', async () => {
    const user = userEvent.setup()
    render(<FileUpload {...defaultProps} acceptedTypes=".jpg,.png,.pdf" />)

    const imageFile = new File(['image data'], 'test.jpg', { type: 'image/jpeg' })
    const input = document.querySelector('input[type="file"]')

    if (input) {
      await user.upload(input as HTMLInputElement, imageFile)

      await waitFor(() => {
        expect(screen.getByTestId('image-icon')).toBeInTheDocument()
      })
    }
  })

  it('should display file icon for documents', async () => {
    const user = userEvent.setup()
    render(<FileUpload {...defaultProps} />)

    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]')

    if (input) {
      await user.upload(input as HTMLInputElement, file)

      await waitFor(() => {
        expect(screen.getByTestId('file-icon')).toBeInTheDocument()
      })
    }
  })
})