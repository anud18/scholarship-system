"use client"

import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { AlertCircle, Plus } from "lucide-react"
import { StudentRosterPreview } from "./StudentRosterPreview"
import { CreateScheduleDialog } from "../create-schedule-dialog"

interface CreateSchedulePromptProps {
  configName: string
  configId: number
  onScheduleCreated?: () => void
}

export function CreateSchedulePrompt({ configName, configId, onScheduleCreated }: CreateSchedulePromptProps) {
  return (
    <div className="space-y-6">
      {/* Student Preview Section */}
      <div>
        <h3 className="text-lg font-semibold mb-3">預覽造冊學生資料</h3>
        <p className="text-sm text-muted-foreground mb-4">
          以下是目前符合資格的學生清單,建立排程後將依此資料自動產生造冊檔案
        </p>
        <StudentRosterPreview configId={configId} />
      </div>

      {/* Create Schedule Prompt Section */}
      <Card className="border-dashed border-2">
        <CardContent className="flex flex-col items-center justify-center p-12 text-center">
          <div className="rounded-full bg-muted p-4 mb-4">
            <AlertCircle className="h-12 w-12 text-muted-foreground" />
          </div>

          <h3 className="text-xl font-semibold mb-2">尚未建立排程</h3>

          <p className="text-muted-foreground mb-2">
            獎學金配置「{configName}」尚未設定造冊排程
          </p>

          <p className="text-sm text-muted-foreground mb-6">
            請先建立排程以啟用自動造冊功能
          </p>

          <CreateScheduleDialog
            preselectedConfigId={configId}
            hideConfigSelector={true}
            onScheduleCreated={onScheduleCreated || (() => {})}
            customTrigger={
              <Button size="lg">
                <Plus className="mr-2 h-5 w-5" />
                建立排程
              </Button>
            }
          />

          <Alert className="mt-6 max-w-md">
            <AlertDescription className="text-sm">
              建立排程後,系統將自動依照設定的週期產生造冊檔案。 <br />
              您也可以隨時手動觸發造冊產生。
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    </div>
  )
}
