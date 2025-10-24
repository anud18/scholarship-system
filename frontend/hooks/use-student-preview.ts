import { useState, useCallback, useRef } from 'react';
import { createCollegeApi } from '@/lib/api/modules/college';

interface StudentPreviewBasic {
  // === 學籍資料 ===
  std_stdcode: string;           // 學號
  std_cname: string;             // 中文姓名
  std_ename?: string;            // 英文姓名
  std_pid: string;               // 身分證字號
  std_bdate?: string;            // 生日

  // === 學院系所 ===
  std_academyno: string;         // 學院代碼
  std_depno: string;             // 系所代碼

  // === 學位與狀態 ===
  std_degree: number;            // 學位別
  std_studingstatus: number;     // 在學狀態
  mgd_title: string;             // 學籍狀態中文

  // === 入學資訊 ===
  std_enrollyear: number;        // 入學年度
  std_enrollterm: number;        // 入學學期
  std_enrolltype: number;        // 入學方式
  std_termcount: number;         // 學期數
  std_highestschname?: string;   // 最高學歷學校

  // === 個人資訊 ===
  std_sex: number;               // 性別 (1:男, 2:女)
  std_nation?: string;           // 國籍
  std_identity: number;          // 學生身分
  std_schoolid: number;          // 在學身分
  std_overseaplace?: string;     // 僑居地
  ToDoctor?: number;             // 是否直升博士

  // === 聯絡資訊 ===
  com_email: string;             // Email
  com_cellphone?: string;        // 手機號碼
  com_commadd?: string;          // 通訊地址
}

interface StudentTermData {
  // Basic term info
  academic_year: string;
  term: string;
  term_count?: number;

  // Academic performance
  gpa?: number;
  ascore_gpa?: number;

  // Rankings
  placings?: number;
  placings_rate?: number;
  dept_placing?: number;
  dept_placing_rate?: number;

  // Student status
  studying_status?: number;
  degree?: number;

  // Academic organization
  academy_no?: string;
  academy_name?: string;
  dept_no?: string;
  dept_name?: string;
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
