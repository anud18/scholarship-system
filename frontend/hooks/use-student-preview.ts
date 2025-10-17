import { useState, useCallback, useRef } from 'react';
import { createCollegeApi } from '@/lib/api/modules/college';

interface StudentPreviewBasic {
  student_id: string;
  student_name: string;
  department_name?: string;
  academy_name?: string;
  term_count?: number;
  degree?: string;
  enrollyear?: string;
  sex?: string;
}

interface StudentTermData {
  academic_year: string;
  term: string;
  gpa?: number;
  credits?: number;
  rank?: number;
}

interface StudentPreviewData {
  basic: StudentPreviewBasic;
  recent_terms: StudentTermData[];
}

interface UseStudentPreviewReturn {
  previewData: StudentPreviewData | null;
  isLoading: boolean;
  error: string | null;
  fetchPreview: (studentId: string, academicYear?: number) => Promise<void>;
}

// Cache to store fetched preview data
const previewCache = new Map<string, StudentPreviewData>();

const collegeApi = createCollegeApi();

export function useStudentPreview(): UseStudentPreviewReturn {
  const [previewData, setPreviewData] = useState<StudentPreviewData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchPreview = useCallback(async (studentId: string, academicYear?: number) => {
    // Check cache first
    const cacheKey = `${studentId}-${academicYear || 'no-year'}`;
    const cached = previewCache.get(cacheKey);

    if (cached) {
      setPreviewData(cached);
      setIsLoading(false);
      setError(null);
      return;
    }

    // Cancel previous request if exists
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();
    setIsLoading(true);
    setError(null);

    try {
      const result = await collegeApi.getStudentPreview(studentId, academicYear);

      if (result.success && result.data) {
        const data = result.data as StudentPreviewData;

        // Cache the result
        previewCache.set(cacheKey, data);

        setPreviewData(data);
        setError(null);
      } else {
        throw new Error(result.message || 'Failed to load student preview');
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // Request was cancelled, ignore
        return;
      }

      console.error('Error fetching student preview:', err);
      setError(err.message || 'Failed to load student preview');
      setPreviewData(null);
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  }, []);

  return {
    previewData,
    isLoading,
    error,
    fetchPreview,
  };
}
