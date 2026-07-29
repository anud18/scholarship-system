---
name: file-upload-preview
description: Architecture and required HTTP headers for the file upload/preview chain (Frontend → Next.js proxy → FastAPI → MinIO/RustFS). Use when adding or debugging document upload, file download, or in-browser PDF/image preview — especially when a PDF viewer errors, falsely reports "password protected", truncates, or a file URL 403s/404s through the proxy.
---

# File Upload & Preview Architecture

## Three-Layer Architecture
```
Frontend → Next.js Proxy → FastAPI → MinIO
```

**Why Next.js Proxy?**
- Token authentication handling
- Internal Docker network communication
- CORS management
- Centralized error handling

## Critical Implementation Rules
1. **Store object_name, not full URL** in database
2. **Always use Next.js proxy** for file access (never direct MinIO URLs)
3. **Pass token via query parameter** for authentication
4. **Use INTERNAL_API_URL** for Docker network communication
5. **Preserve all headers** from backend when proxying

## Required HTTP Headers for PDF Preview
When proxying files through Next.js, preserve these headers:

```typescript
return new NextResponse(fileBuffer, {
  headers: {
    "Content-Type": contentType,                           // File type
    "Content-Disposition": contentDisposition,             // Preserve from backend
    "Content-Length": fileBuffer.byteLength.toString(),    // File size (REQUIRED)
    "Accept-Ranges": "bytes",                              // Range support
    "Cache-Control": "private, max-age=3600",
  },
});
```

**CRITICAL**: Missing `Content-Length` or incomplete `Content-Disposition` can cause PDF viewer errors (including false "password protected" errors).

## Environment Variables

The object-storage and proxy env vars (`MINIO_ENDPOINT`, `MINIO_BUCKET`, `NEXT_PUBLIC_API_URL`, `INTERNAL_API_URL`) are declared in `docker-compose.dev.yml` — read them there rather than assuming values. Note `INTERNAL_API_URL` points at the Docker-internal `backend` host, not `localhost`.
