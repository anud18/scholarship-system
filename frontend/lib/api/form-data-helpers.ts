/**
 * Type-safe helpers for FormData handling with OpenAPI
 *
 * OpenAPI 3.0 represents file uploads as `type: "string", format: "binary"` in the schema,
 * but at runtime, we need to pass FormData objects for multipart/form-data endpoints.
 *
 * These utilities provide type-safe FormData handling while maintaining compatibility
 * with openapi-fetch's type system.
 */

import type { paths } from './generated/schema';

/**
 * Type utility for multipart/form-data body type assertions
 *
 * OpenAPI schemas represent file uploads as `{ file: string }` with format: "binary",
 * but at runtime we must pass FormData. This type allows safe type assertions.
 *
 * Usage: `body: formData as MultipartFormData<ExpectedBodyType>`
 */
export type MultipartFormData<T> = any;

/**
 * Create FormData for file upload endpoints
 * Provides runtime type checking and clear error messages
 *
 * @example
 * ```ts
 * const formData = createFileUploadFormData({
 *   file: myFile,
 *   file_type: 'document'
 * });
 *
 * const response = await typedClient.raw.POST('/api/v1/applications/{id}/files/upload', {
 *   params: { path: { id: 123 }, query: { file_type: 'document' } },
 *   body: formData as MultipartFormData<BodyType>
 * });
 * ```
 */
export function createFileUploadFormData(data: {
  file: File;
  [key: string]: string | File;
}): FormData {
  const formData = new FormData();

  for (const [key, value] of Object.entries(data)) {
    if (value instanceof File) {
      formData.append(key, value);
    } else if (value !== undefined && value !== null) {
      formData.append(key, String(value));
    }
  }

  return formData;
}

/**
 * Type guard to check if a value is FormData
 */
export function isFormData(value: any): value is FormData {
  return value instanceof FormData;
}

/**
 * Helper to create properly typed FormData for specific OpenAPI endpoints
 * This provides better type safety than plain FormData
 */
export class TypedFormData<T extends Record<string, any> = Record<string, any>> {
  private formData: FormData;

  constructor(data?: T) {
    this.formData = new FormData();
    if (data) {
      for (const [key, value] of Object.entries(data)) {
        this.append(key, value);
      }
    }
  }

  append(key: keyof T, value: any): this {
    if (value instanceof File || value instanceof Blob) {
      this.formData.append(String(key), value);
    } else if (value !== undefined && value !== null) {
      this.formData.append(String(key), String(value));
    }
    return this;
  }

  get(): FormData {
    return this.formData;
  }

  /**
   * Cast to type compatible with openapi-fetch body parameter
   * This is safer than `as any` because it's explicitly typed
   */
  asBody<BodyType>(): MultipartFormData<BodyType> {
    return this.formData as MultipartFormData<BodyType>;
  }
}

/**
 * Convenience function to create typed FormData
 *
 * @example
 * ```ts
 * const formData = typedFormData({ file: myFile, type: 'document' });
 * const response = await typedClient.raw.POST('/api/v1/upload', {
 *   body: formData.asBody<ExpectedBodyType>()
 * });
 * ```
 */
export function typedFormData<T extends Record<string, any>>(data?: T): TypedFormData<T> {
  return new TypedFormData(data);
}
