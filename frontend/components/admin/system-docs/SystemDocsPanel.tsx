"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FileText, Loader2, Upload } from "lucide-react";
import apiClient from "@/lib/api";
import { toast } from "sonner";

export function SystemDocsPanel() {
  const [regulationsFile, setRegulationsFile] = useState<File | null>(null);
  const [sampleDocFile, setSampleDocFile] = useState<File | null>(null);
  const [uploadingRegulations, setUploadingRegulations] = useState(false);
  const [uploadingSampleDoc, setUploadingSampleDoc] = useState(false);
  const [currentRegulationsName, setCurrentRegulationsName] = useState<string>("");
  const [currentSampleDocName, setCurrentSampleDocName] = useState<string>("");

  useEffect(() => {
    apiClient.systemSettings.getPublicDocs().then((res) => {
      if (res.success && res.data) {
        if (res.data.regulations_url)
          setCurrentRegulationsName(
            res.data.regulations_url.split("/").pop() || ""
          );
        if (res.data.sample_document_url)
          setCurrentSampleDocName(
            res.data.sample_document_url.split("/").pop() || ""
          );
      }
    });
  }, []);

  const handleUploadRegulations = async () => {
    if (!regulationsFile) return;
    setUploadingRegulations(true);
    try {
      const res = await apiClient.systemSettings.uploadRegulations(regulationsFile);
      if (res.success) {
        toast.success("獎學金要點上傳成功");
        setCurrentRegulationsName(res.data?.object_name?.split("/").pop() || "");
        setRegulationsFile(null);
      } else {
        toast.error(res.message || "上傳失敗");
      }
    } catch {
      toast.error("上傳失敗");
    } finally {
      setUploadingRegulations(false);
    }
  };

  const handleUploadSampleDoc = async () => {
    if (!sampleDocFile) return;
    setUploadingSampleDoc(true);
    try {
      const res = await apiClient.systemSettings.uploadSampleDocument(sampleDocFile);
      if (res.success) {
        toast.success("申請文件範例檔上傳成功");
        setCurrentSampleDocName(res.data?.object_name?.split("/").pop() || "");
        setSampleDocFile(null);
      } else {
        toast.error(res.message || "上傳失敗");
      }
    } catch {
      toast.error("上傳失敗");
    } finally {
      setUploadingSampleDoc(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5" />
          系統文件管理
        </CardTitle>
        <CardDescription>
          上傳供學生及審核人員參閱的全域文件
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-8">
        {/* 獎學金要點 */}
        <div className="space-y-3">
          <Label className="text-base font-semibold">獎學金要點</Label>
          {currentRegulationsName && (
            <p className="text-sm text-gray-600">
              目前檔案：<span className="font-mono">{currentRegulationsName}</span>
            </p>
          )}
          <div className="flex items-center gap-3">
            <Input
              type="file"
              accept=".pdf,.doc,.docx"
              onChange={(e) => setRegulationsFile(e.target.files?.[0] || null)}
              className="max-w-xs"
            />
            <Button
              onClick={handleUploadRegulations}
              disabled={!regulationsFile || uploadingRegulations}
            >
              {uploadingRegulations ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  上傳中...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4 mr-2" />
                  上傳
                </>
              )}
            </Button>
          </div>
        </div>

        {/* 申請文件範例檔 */}
        <div className="space-y-3">
          <Label className="text-base font-semibold">申請文件範例檔</Label>
          {currentSampleDocName && (
            <p className="text-sm text-gray-600">
              目前檔案：<span className="font-mono">{currentSampleDocName}</span>
            </p>
          )}
          <div className="flex items-center gap-3">
            <Input
              type="file"
              accept=".pdf,.doc,.docx"
              onChange={(e) => setSampleDocFile(e.target.files?.[0] || null)}
              className="max-w-xs"
            />
            <Button
              onClick={handleUploadSampleDoc}
              disabled={!sampleDocFile || uploadingSampleDoc}
            >
              {uploadingSampleDoc ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  上傳中...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4 mr-2" />
                  上傳
                </>
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
