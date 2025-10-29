/**
 * Batch Bank Verification Component (Admin)
 *
 * Allows administrators to:
 * - Select multiple applications for verification
 * - Start async batch verification
 * - Monitor progress in real-time
 * - View results and manual review needs
 */

'use client';

import { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle, Clock, XCircle, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { createBankVerificationApi } from '@/lib/api/modules/bank-verification';
import type { BankVerificationTask } from '@/lib/api/modules/bank-verification';

const api = createBankVerificationApi();

interface BatchBankVerificationProps {
  applicationIds: number[];
  onComplete?: (taskId: string, results: any) => void;
  onNeedsReview?: (applicationIds: number[]) => void;
}

export function BatchBankVerification({
  applicationIds,
  onComplete,
  onNeedsReview,
}: BatchBankVerificationProps) {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [task, setTask] = useState<BankVerificationTask | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Poll for task status updates
  useEffect(() => {
    if (!taskId || task?.is_completed) return;

    const interval = setInterval(async () => {
      try {
        const response = await api.getVerificationTaskStatus(taskId);
        if (response.success && response.data) {
          setTask(response.data);

          // Call onComplete when task finishes
          if (response.data.is_completed && onComplete) {
            onComplete(taskId, response.data.results);
          }

          // Call onNeedsReview if there are applications needing review
          if (response.data.needs_review_count > 0 && onNeedsReview) {
            const needsReviewIds = Object.entries(response.data.results || {})
              .filter(([, result]: [string, any]) => result.status === 'needs_manual_review')
              .map(([appId]) => parseInt(appId));
            onNeedsReview(needsReviewIds);
          }
        }
      } catch (err) {
        console.error('Failed to fetch task status:', err);
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [taskId, task?.is_completed, onComplete, onNeedsReview]);

  const startBatchVerification = async () => {
    setIsStarting(true);
    setError(null);

    try {
      const response = await api.startBatchVerificationAsync(applicationIds);
      if (response.success && response.data) {
        setTaskId(response.data.task_id);
      } else {
        setError(response.message || '啟動批次驗證失敗');
      }
    } catch (err) {
      setError('啟動批次驗證時發生錯誤');
      console.error(err);
    } finally {
      setIsStarting(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return <Badge variant="secondary">等待中</Badge>;
      case 'processing':
        return <Badge variant="default" className="bg-blue-500">處理中</Badge>;
      case 'completed':
        return <Badge variant="default" className="bg-green-500">已完成</Badge>;
      case 'failed':
        return <Badge variant="destructive">失敗</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  // No task started yet
  if (!taskId && !task) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>批次銀行帳戶驗證</CardTitle>
          <CardDescription>
            將對 {applicationIds.length} 個申請進行 AI OCR 驗證
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-2">
            <p className="text-sm text-gray-600">
              批次驗證將會：
            </p>
            <ul className="text-sm text-gray-600 list-disc list-inside space-y-1">
              <li>使用 AI OCR 自動提取帳本封面資訊</li>
              <li>比對學生填寫的帳號與 OCR 結果（帳號需 100% 精確匹配）</li>
              <li>比對戶名（允許 80% 相似度，考慮 OCR 誤差）</li>
              <li>自動標記高信心度通過的申請</li>
              <li>標記需要人工審核的申請</li>
            </ul>
          </div>

          <Button
            onClick={startBatchVerification}
            disabled={isStarting || applicationIds.length === 0}
            className="w-full"
          >
            {isStarting ? '啟動中...' : `開始批次驗證（${applicationIds.length} 個申請）`}
          </Button>
        </CardContent>
      </Card>
    );
  }

  // Task in progress or completed
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          批次驗證進度
          {task && getStatusBadge(task.status)}
        </CardTitle>
        <CardDescription>
          任務 ID: {taskId}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {task && (
          <>
            {/* Progress bar */}
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>進度：{task.processed_count} / {task.total_count}</span>
                <span className="font-medium">{Math.round(task.progress_percentage || 0)}%</span>
              </div>
              <Progress value={task.progress_percentage || 0} className="h-2" />
            </div>

            {/* Statistics */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3 bg-green-50 rounded-lg">
                <div className="flex items-center gap-2 text-green-700">
                  <CheckCircle className="h-4 w-4" />
                  <span className="text-sm font-medium">通過</span>
                </div>
                <p className="text-2xl font-bold text-green-900 mt-1">{task.verified_count}</p>
              </div>

              <div className="p-3 bg-yellow-50 rounded-lg">
                <div className="flex items-center gap-2 text-yellow-700">
                  <Eye className="h-4 w-4" />
                  <span className="text-sm font-medium">需審核</span>
                </div>
                <p className="text-2xl font-bold text-yellow-900 mt-1">{task.needs_review_count}</p>
              </div>

              <div className="p-3 bg-red-50 rounded-lg">
                <div className="flex items-center gap-2 text-red-700">
                  <XCircle className="h-4 w-4" />
                  <span className="text-sm font-medium">失敗</span>
                </div>
                <p className="text-2xl font-bold text-red-900 mt-1">{task.failed_count}</p>
              </div>

              <div className="p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-2 text-gray-700">
                  <Clock className="h-4 w-4" />
                  <span className="text-sm font-medium">跳過</span>
                </div>
                <p className="text-2xl font-bold text-gray-900 mt-1">{task.skipped_count || 0}</p>
              </div>
            </div>

            {/* Status messages */}
            {task.is_running && (
              <Alert className="border-blue-200 bg-blue-50">
                <Clock className="h-4 w-4 text-blue-600" />
                <AlertDescription className="text-blue-800">
                  正在處理中，請稍候...
                </AlertDescription>
              </Alert>
            )}

            {task.is_completed && !task.error_message && (
              <Alert className="border-green-200 bg-green-50">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <AlertDescription className="text-green-800">
                  批次驗證已完成！
                  {task.needs_review_count > 0 && (
                    <span className="block mt-1">
                      有 {task.needs_review_count} 個申請需要人工審核。
                    </span>
                  )}
                </AlertDescription>
              </Alert>
            )}

            {task.error_message && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{task.error_message}</AlertDescription>
              </Alert>
            )}

            {/* Timestamps */}
            {task.is_completed && (
              <div className="text-xs text-gray-500 space-y-1">
                <p>開始時間：{task.started_at ? new Date(task.started_at).toLocaleString('zh-TW') : '-'}</p>
                <p>完成時間：{task.completed_at ? new Date(task.completed_at).toLocaleString('zh-TW') : '-'}</p>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
