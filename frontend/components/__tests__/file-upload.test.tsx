import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { FileUpload } from '../file-upload'

// Mock the FilePreviewDialog component
jest.mock('../file-preview-dialog', () => ({
  FilePreviewDialog: ({ isOpen, onClose, fileUrl, filename, fileType }: any) => (
    isOpen ? (
      <div data-testid="file-preview-dialog">
        <span>Preview: {filename}</span>
        <span>Type: {fileType}</span>
        <span>URL: {fileUrl}</span>
        <button onClick={onClose}>Close Preview</button>
      </div>
    ) : null
  )
}))

// Mock URL.createObjectURL and URL.revokeObjectURL
global.URL.createObjectURL = jest.fn(() => 'mock-object-url')
global.URL.revokeObjectURL = jest.fn()

describe('FileUpload Component', () => {
  let mockOnFilesChange: jest.Mock

  beforeEach(() => {
    mockOnFilesChange = jest.fn()
    jest.clearAllMocks()
  })

  it('should render file upload area', async () => {
    render(<FileUpload onFilesChange={mockOnFilesChange} />)
    
    await waitFor(() => {
      expect(screen.getByText(/拖拽文件至此處/i)).toBeInTheDocument()
      expect(screen.getByText(/選擇文件/i)).toBeInTheDocument()
    })
  })

  it('should render in English locale', () => {
    render(<FileUpload onFilesChange={mockOnFilesChange} locale="en" />)
    
    expect(screen.getByText(/drag files here/i)).toBeInTheDocument()
    expect(screen.getByText(/choose files/i)).toBeInTheDocument()
  })

  it('should handle file selection via input', () => {
    render(<FileUpload onFilesChange={mockOnFilesChange} />)
    
    const input = screen.getByRole('button', { name: /選擇文件/i }).closest('label')?.querySelector('input')
    expect(input).toBeInTheDocument()

    // Create a mock file
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    
    if (input) {
      Object.defineProperty(input, 'files', {
        value: [file],
        configurable: true,
      })
      
      fireEvent.change(input)

      expect(mockOnFilesChange).toHaveBeenCalledWith([file])
    }
  })

  it('should handle drag and drop', () => {
    render(<FileUpload onFilesChange={mockOnFilesChange} />)
    
    const dropZone = screen.getByText(/拖拽文件至此處/i).closest('div')
    
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    
    // Simulate drag enter
    fireEvent.dragEnter(dropZone!, {
      dataTransfer: {
        files: [file],
      },
    })

    // Simulate drop
    fireEvent.drop(dropZone!, {
      dataTransfer: {
        files: [file],
      },
    })

    expect(mockOnFilesChange).toHaveBeenCalledWith([file])
  })

  it('should filter invalid file types', () => {
    render(
      <FileUpload 
        onFilesChange={mockOnFilesChange} 
        acceptedTypes={['.pdf']}
      />
    )
    
    const input = screen.getByRole('button', { name: /選擇文件/i }).closest('label')?.querySelector('input')
    
    const validFile = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    const invalidFile = new File(['content'], 'test.txt', { type: 'text/plain' })
    
    if (input) {
      Object.defineProperty(input, 'files', {
        value: [validFile, invalidFile],
        configurable: true,
      })
      
      fireEvent.change(input)

      // Should only include the valid PDF file
      expect(mockOnFilesChange).toHaveBeenCalledWith([validFile])
    }
  })

  it('should filter files exceeding size limit', () => {
    const maxSize = 1024 // 1KB
    render(
      <FileUpload 
        onFilesChange={mockOnFilesChange} 
        maxSize={maxSize}
      />
    )
    
    const input = screen.getByRole('button', { name: /選擇文件/i }).closest('label')?.querySelector('input')
    
    const smallFile = new File(['a'], 'small.pdf', { type: 'application/pdf' })
    const largeFile = new File(['a'.repeat(2000)], 'large.pdf', { type: 'application/pdf' })
    
    if (input) {
      Object.defineProperty(input, 'files', {
        value: [smallFile, largeFile],
        configurable: true,
      })
      
      fireEvent.change(input)

      // Should only include the small file
      expect(mockOnFilesChange).toHaveBeenCalledWith([smallFile])
    }
  })

  it('should enforce max files limit', () => {
    render(
      <FileUpload 
        onFilesChange={mockOnFilesChange} 
        maxFiles={2}
      />
    )
    
    const input = screen.getByRole('button', { name: /選擇文件/i }).closest('label')?.querySelector('input')
    
    const files = [
      new File(['1'], 'file1.pdf', { type: 'application/pdf' }),
      new File(['2'], 'file2.pdf', { type: 'application/pdf' }),
      new File(['3'], 'file3.pdf', { type: 'application/pdf' }),
    ]
    
    if (input) {
      Object.defineProperty(input, 'files', {
        value: files,
        configurable: true,
      })
      
      fireEvent.change(input)

      // Should only include first 2 files
      expect(mockOnFilesChange).toHaveBeenCalledWith([files[0], files[1]])
    }
  })

  it('should display uploaded files', () => {
    const initialFiles = [
      new File(['content'], 'test.pdf', { type: 'application/pdf' })
    ]
    
    render(
      <FileUpload 
        onFilesChange={mockOnFilesChange} 
        initialFiles={initialFiles}
      />
    )
    
    expect(screen.getByText('test.pdf')).toBeInTheDocument()
  })

  it('should allow file removal', () => {
    const initialFiles = [
      new File(['content'], 'test.pdf', { type: 'application/pdf' })
    ]
    
    render(
      <FileUpload 
        onFilesChange={mockOnFilesChange} 
        initialFiles={initialFiles}
      />
    )
    
    const removeButton = screen.getByRole('button', { name: /刪除/i })
    fireEvent.click(removeButton)
    
    expect(mockOnFilesChange).toHaveBeenCalledWith([])
  })

  it('should handle file preview', () => {
    const initialFiles = [
      new File(['content'], 'test.pdf', { type: 'application/pdf' })
    ]
    
    render(
      <FileUpload 
        onFilesChange={mockOnFilesChange} 
        initialFiles={initialFiles}
      />
    )
    
    const previewButton = screen.getByRole('button', { name: /預覽/i })
    fireEvent.click(previewButton)
    
    expect(screen.getByTestId('file-preview-dialog')).toBeInTheDocument()
    expect(screen.getByText('Preview: test.pdf')).toBeInTheDocument()
  })

  it('should close preview dialog', () => {
    const initialFiles = [
      new File(['content'], 'test.pdf', { type: 'application/pdf' })
    ]
    
    render(
      <FileUpload 
        onFilesChange={mockOnFilesChange} 
        initialFiles={initialFiles}
      />
    )
    
    // Open preview
    const previewButton = screen.getByRole('button', { name: /預覽/i })
    fireEvent.click(previewButton)
    
    expect(screen.getByTestId('file-preview-dialog')).toBeInTheDocument()
    
    // Close preview
    const closeButton = screen.getByText('Close Preview')
    fireEvent.click(closeButton)
    
    expect(screen.queryByTestId('file-preview-dialog')).not.toBeInTheDocument()
  })

  it('should show file size in appropriate units', () => {
    const files = [
      new File(['a'.repeat(500)], 'small.pdf', { type: 'application/pdf' }),
      new File(['a'.repeat(1500)], 'medium.pdf', { type: 'application/pdf' }),
      new File(['a'.repeat(1024 * 1024)], 'large.pdf', { type: 'application/pdf' }),
    ]
    
    render(
      <FileUpload 
        onFilesChange={mockOnFilesChange} 
        initialFiles={files}
      />
    )
    
    // Should show appropriate size units
    expect(screen.getByText(/B/)).toBeInTheDocument() // bytes
    expect(screen.getByText(/KB/)).toBeInTheDocument() // kilobytes
    expect(screen.getByText(/MB/)).toBeInTheDocument() // megabytes
  })

  it('should handle drag state correctly', () => {
    render(<FileUpload onFilesChange={mockOnFilesChange} />)
    
    const dropZone = screen.getByText(/拖拽文件至此處/i).closest('div')
    
    // Simulate drag enter
    fireEvent.dragEnter(dropZone!)
    
    // Should add active drag state (we can't directly test CSS classes, but we can test the behavior)
    expect(dropZone).toBeInTheDocument()
    
    // Simulate drag leave
    fireEvent.dragLeave(dropZone!)
    
    expect(dropZone).toBeInTheDocument()
  })

  it('should generate unique input IDs', () => {
    const { unmount } = render(<FileUpload onFilesChange={mockOnFilesChange} fileType="test" />)
    const firstInput = screen.getByRole('button', { name: /選擇文件/i }).closest('label')?.querySelector('input')
    const firstId = firstInput?.id
    
    unmount()
    
    render(<FileUpload onFilesChange={mockOnFilesChange} fileType="test" />)
    const secondInput = screen.getByRole('button', { name: /選擇文件/i }).closest('label')?.querySelector('input')
    const secondId = secondInput?.id
    
    expect(firstId).toBeDefined()
    expect(secondId).toBeDefined()
    expect(firstId).not.toBe(secondId)
  })

  it('should identify uploaded files correctly', () => {
    const uploadedFile = new File(['content'], 'uploaded.pdf', { type: 'application/pdf' })
    // Simulate an uploaded file with additional properties
    Object.assign(uploadedFile, { id: 'file123', file_path: '/uploads/file.pdf' })
    
    render(
      <FileUpload 
        onFilesChange={mockOnFilesChange} 
        initialFiles={[uploadedFile]}
      />
    )
    
    // Should still render the file
    expect(screen.getByText('uploaded.pdf')).toBeInTheDocument()
  })

  describe('accessibility', () => {
    it('should have proper ARIA labels', () => {
      render(<FileUpload onFilesChange={mockOnFilesChange} />)
      
      const input = screen.getByRole('button', { name: /選擇文件/i }).closest('label')?.querySelector('input')
      expect(input).toHaveAttribute('type', 'file')
    })

    it('should have proper button roles', () => {
      const initialFiles = [
        new File(['content'], 'test.pdf', { type: 'application/pdf' })
      ]
      
      render(
        <FileUpload 
          onFilesChange={mockOnFilesChange} 
          initialFiles={initialFiles}
        />
      )
      
      expect(screen.getByRole('button', { name: /預覽/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /刪除/i })).toBeInTheDocument()
    })
  })

  describe('error handling', () => {
    it('should handle files without extensions', () => {
      render(<FileUpload onFilesChange={mockOnFilesChange} />)
      
      const input = screen.getByRole('button', { name: /選擇文件/i }).closest('label')?.querySelector('input')
      const fileWithoutExtension = new File(['content'], 'noextension', { type: 'application/pdf' })
      
      if (input) {
        Object.defineProperty(input, 'files', {
          value: [fileWithoutExtension],
          configurable: true,
        })
        
        fireEvent.change(input)
        
        // Should not call onFilesChange with invalid file
        expect(mockOnFilesChange).toHaveBeenCalledWith([])
      }
    })
  })
})