import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const fileId = searchParams.get('fileId')
    const filename = searchParams.get('filename')
    const type = searchParams.get('type')
    const applicationId = searchParams.get('applicationId')
    const userId = searchParams.get('userId')
    const token = searchParams.get('token')

    if (!fileId) {
      return NextResponse.json(
        { error: 'File ID is required' },
        { status: 400 }
      )
    }

    // For user profile documents, userId can be used instead of applicationId
    if (!applicationId && !userId) {
      return NextResponse.json(
        { error: 'Application ID or User ID is required' },
        { status: 400 }
      )
    }

    if (!token) {
      return NextResponse.json(
        { error: 'Access token is required' },
        { status: 400 }
      )
    }

    // 使用後端的下載端點
    let backendUrl
    if (applicationId) {
      // Application file download
      backendUrl = `${process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL}/api/v1/files/applications/${applicationId}/files/${fileId}/download?token=${token}`
    } else if (userId) {
      // User profile file download (e.g., bank document)
      backendUrl = `${process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL}/api/v1/user-profiles/files/bank_documents/${fileId}?token=${token}`
    } else {
      return NextResponse.json(
        { error: 'Invalid file context' },
        { status: 400 }
      )
    }

    console.log('Download API called:', {
      fileId,
      applicationId,
      userId,
      backendUrl
    })

    // 從後端獲取文件
    const response = await fetch(backendUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })

    if (!response.ok) {
      console.error('Backend response error:', response.status, response.statusText)
      return NextResponse.json(
        { error: 'Failed to fetch file from backend' },
        { status: response.status }
      )
    }

    // 獲取文件數據
    const fileBuffer = await response.arrayBuffer()
    const contentType = response.headers.get('content-type') || 'application/octet-stream'

    // 處理中文文件名編碼
    let contentDisposition = 'attachment'
    if (filename) {
      // 使用 encodeURIComponent 來正確編碼中文文件名
      const encodedFilename = encodeURIComponent(filename)
      contentDisposition = `attachment; filename*=UTF-8''${encodedFilename}`
    }

    // 返回文件給用戶
    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Content-Disposition': contentDisposition,
        'Cache-Control': 'no-cache',
      },
    })
  } catch (error) {
    console.error('File download error:', error)
    return NextResponse.json(
      { error: 'Failed to download file' },
      { status: 500 }
    )
  }
}
