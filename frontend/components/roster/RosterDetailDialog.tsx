"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Loader2 } from "lucide-react";
import { apiClient } from "@/lib/api";

interface Period {
  label: string;
  status:
    | "completed"
    | "waiting"
    | "failed"
    | "processing"
    | "draft"
    | "locked";
  roster_id?: number;
  roster_code?: string;
  roster_status?: string;
  error_message?: string;
  completed_at?: string;
  total_amount?: number;
  qualified_count?: number;
  next_schedule?: string;
  period_start_date?: string;
  period_end_date?: string;
  sub_type?: string | null;
  allocation_year?: number | null;
}

interface RosterDetailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  period: Period;
  configId: number;
}

interface RosterItem {
  student_name: string;
  student_id: string;
  student_id_number: string;
  student_email?: string;
  college_code?: string;
  college_name?: string;
  department_name?: string;
  scholarship_subtype: string;
  scholarship_amount: number;
  allocation_year?: number;
  bank_account?: string;
  is_included: boolean;
  application_identity?: string;
  allocated_sub_type?: string;
}

export function RosterDetailDialog({
  open,
  onOpenChange,
  period,
  configId,
}: RosterDetailDialogProps) {
  const [loading, setLoading] = useState(true);
  const [rosterItems, setRosterItems] = useState<RosterItem[]>([]);
  const [selectedCollege, setSelectedCollege] = useState<string>("");
  const [hasMatrix, setHasMatrix] = useState(false);

  useEffect(() => {
    if (open && period.roster_id) {
      loadRosterItems();
    }
  }, [open, period.roster_id]);

  const loadRosterItems = async () => {
    if (!period.roster_id) return;

    setLoading(true);
    try {
      const response = await apiClient.request(
        `/payment-rosters/${period.roster_id}/items`,
        { method: "GET" }
      );

      if (response.success && response.data) {
        const items = response.data.items || response.data;
        setRosterItems(items);

        // Check if has matrix (multiple colleges)
        const colleges = new Set(
          items.map((item: RosterItem) => item.college_code).filter(Boolean)
        );
        setHasMatrix(colleges.size > 1);

        if (colleges.size > 0) {
          const firstCollege = Array.from(colleges)[0];
          setSelectedCollege(firstCollege as string);
        }
      }
    } catch (error) {
      console.error("Failed to load roster items:", error);
    } finally {
      setLoading(false);
    }
  };

  const getItemsByCollege = (college: string): RosterItem[] => {
    return rosterItems.filter(item => item.college_code === college);
  };

  const colleges = Array.from(
    new Set(rosterItems.map(item => item.college_code).filter(Boolean))
  ).sort() as string[];

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat("zh-TW", {
      style: "currency",
      currency: "TWD",
      minimumFractionDigits: 0,
    }).format(amount);
  };

  /** Find display name for a college code from the loaded items */
  const getCollegeDisplayName = (code: string): string => {
    const item = rosterItems.find(i => i.college_code === code);
    return item?.college_name || code;
  };

  const renderStudentTable = (items: RosterItem[]) => {
    const includedItems = items.filter(item => item.is_included);

    if (includedItems.length === 0) {
      return (
        <div className="text-center py-8 text-muted-foreground">
          此學院無納入造冊的學生
        </div>
      );
    }

    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>姓名</TableHead>
            <TableHead>學號</TableHead>
            <TableHead>系所</TableHead>
            <TableHead>申請身分</TableHead>
            <TableHead>分發獎學金</TableHead>
            <TableHead className="text-right">金額</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {includedItems.map((item, index) => (
            <TableRow key={index}>
              <TableCell className="font-medium">{item.student_name}</TableCell>
              <TableCell className="font-mono text-sm">
                {item.student_id_number}
              </TableCell>
              <TableCell>{item.department_name || "-"}</TableCell>
              <TableCell>
                <Badge
                  variant={
                    item.application_identity?.includes("續領")
                      ? "secondary"
                      : "outline"
                  }
                >
                  {item.application_identity || "-"}
                </Badge>
              </TableCell>
              <TableCell>
                {item.allocated_sub_type ? (
                  <span className="text-sm">
                    {item.allocation_year && (
                      <span className="font-medium">
                        {item.allocation_year}年{" "}
                      </span>
                    )}
                    {item.allocated_sub_type === "nstc"
                      ? "國科會"
                      : item.allocated_sub_type === "moe_1w"
                        ? "教育部(1萬)"
                        : item.allocated_sub_type === "moe_2w"
                          ? "教育部(2萬)"
                          : item.allocated_sub_type}
                  </span>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </TableCell>
              <TableCell className="text-right font-medium">
                {formatCurrency(item.scholarship_amount)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>造冊詳情 - {period.label}</DialogTitle>
          <DialogDescription>
            <span>造冊代碼: {period.roster_code}</span>
            {period.sub_type && (
              <span className="ml-3">
                獎學金類型:{" "}
                <Badge variant="outline" className="ml-1">
                  {period.sub_type}
                </Badge>
              </span>
            )}
            {period.allocation_year && (
              <span className="ml-3">
                配額年度:{" "}
                <Badge variant="secondary" className="ml-1">
                  {period.allocation_year}
                </Badge>
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <span className="ml-2 text-muted-foreground">載入中...</span>
          </div>
        ) : hasMatrix ? (
          <Tabs value={selectedCollege} onValueChange={setSelectedCollege}>
            <TabsList
              className="grid w-full"
              style={{
                gridTemplateColumns: `repeat(${Math.min(colleges.length, 8)}, 1fr)`,
              }}
            >
              {colleges.map(college => {
                const count = getItemsByCollege(college).filter(
                  item => item.is_included
                ).length;
                return (
                  <TabsTrigger key={college} value={college}>
                    {getCollegeDisplayName(college)}
                    <Badge variant="secondary" className="ml-2">
                      {count}
                    </Badge>
                  </TabsTrigger>
                );
              })}
            </TabsList>

            {colleges.map(college => (
              <TabsContent key={college} value={college} className="mt-4">
                {renderStudentTable(getItemsByCollege(college))}
              </TabsContent>
            ))}
          </Tabs>
        ) : (
          <div className="mt-4">{renderStudentTable(rosterItems)}</div>
        )}

        {/* Summary */}
        <div className="mt-4 p-4 bg-muted rounded-lg">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">納入造冊人數:</span>
              <span className="ml-2 font-semibold">
                {rosterItems.filter(item => item.is_included).length} 人
              </span>
            </div>
            <div>
              <span className="text-muted-foreground">總金額:</span>
              <span className="ml-2 font-semibold">
                {formatCurrency(
                  rosterItems
                    .filter(item => item.is_included)
                    .reduce(
                      (sum, item) => sum + Number(item.scholarship_amount),
                      0
                    )
                )}
              </span>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
