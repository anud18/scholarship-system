"use client";

import { useState, useEffect } from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Save, X } from "lucide-react";
import { ScholarshipRule, SubTypeOption, api } from "@/lib/api";

interface ScholarshipRuleModalProps {
  isOpen: boolean;
  onClose: () => void;
  rule?: ScholarshipRule | null;
  scholarshipTypeId: number;
  academicYear: number;
  semester?: string | null;
  onSubmit: (rule: Partial<ScholarshipRule>) => Promise<void>;
  isLoading?: boolean;
}

const RULE_TYPES = [
  { value: "student", label: "學生資料" },
  { value: "student_term", label: "學生學期資料" },
];

const OPERATORS = [
  { value: "==", label: "等於 (==)" },
  { value: "!=", label: "不等於 (!=)" },
  { value: ">", label: "大於 (>)" },
  { value: "<", label: "小於 (<)" },
  { value: ">=", label: "大於等於 (>=)" },
  { value: "<=", label: "小於等於 (<=)" },
  { value: "in", label: "包含於 (in)" },
  { value: "not_in", label: "不包含於 (not_in)" },
  { value: "contains", label: "包含 (contains)" },
  { value: "not_contains", label: "不包含 (not_contains)" },
];

const STUDENT_FIELDS = [
  { value: "std_stdcode", label: "學號 (std_stdcode)" },
  { value: "std_enrollyear", label: "入學年度 (std_enrollyear)" },
  { value: "std_enrollterm", label: "入學學期 (std_enrollterm)" },
  {
    value: "std_highestschname",
    label: "最高學歷學校名稱 (std_highestschname)",
  },
  { value: "std_cname", label: "中文姓名 (std_cname)" },
  { value: "std_ename", label: "英文姓名 (std_ename)" },
  { value: "std_pid", label: "身分證字號 (std_pid)" },
  { value: "std_bdate", label: "出生日期 (std_bdate)" },
  { value: "std_academyno", label: "學院代碼 (std_academyno)" },
  { value: "std_depno", label: "系所代碼 (std_depno)" },
  { value: "std_sex", label: "性別 (std_sex)" },
  { value: "std_nation", label: "國籍 (std_nation)" },
  { value: "std_degree", label: "學位 (std_degree)" },
  { value: "std_enrolltype", label: "入學管道 (std_enrolltype)" },
  { value: "std_identity", label: "身分別 (std_identity)" },
  { value: "std_schoolid", label: "學校身分 (std_schoolid)" },
  { value: "std_overseaplace", label: "僑居地 (std_overseaplace)" },
  { value: "std_termcount", label: "就學期間 (std_termcount)" },
  { value: "std_studingstatus", label: "學籍狀態 (std_studingstatus)" },
  { value: "mgd_title", label: "學籍狀態標題 (mgd_title)" },
  { value: "ToDoctor", label: "是否逕讀博士 (ToDoctor)" },
  { value: "com_commadd", label: "通訊地址 (com_commadd)" },
  { value: "com_email", label: "電子信箱 (com_email)" },
  { value: "com_cellphone", label: "手機號碼 (com_cellphone)" },
];

const STUDENT_TERM_FIELDS = [
  { value: "std_stdcode", label: "學號 (std_stdcode)" },
  { value: "trm_year", label: "學年度 (trm_year)" },
  { value: "trm_term", label: "學期 (trm_term)" },
  { value: "trm_termcount", label: "學期數 (trm_termcount)" },
  { value: "trm_studystatus", label: "就學狀態 (trm_studystatus)" },
  { value: "trm_degree", label: "學期學位 (trm_degree)" },
  { value: "trm_academyno", label: "學期學院代碼 (trm_academyno)" },
  { value: "trm_academyname", label: "學院名稱 (trm_academyname)" },
  { value: "trm_depno", label: "學期系所代碼 (trm_depno)" },
  { value: "trm_depname", label: "系所名稱 (trm_depname)" },
  { value: "trm_placings", label: "總排名 (trm_placings)" },
  { value: "trm_placingsrate", label: "總排名百分比 (trm_placingsrate)" },
  { value: "trm_depplacing", label: "系排名 (trm_depplacing)" },
  { value: "trm_depplacingrate", label: "系排名百分比 (trm_depplacingrate)" },
  { value: "trm_ascore_gpa", label: "GPA (trm_ascore_gpa)" },
];

export function ScholarshipRuleModal({
  isOpen,
  onClose,
  rule,
  scholarshipTypeId,
  academicYear,
  semester,
  onSubmit,
  isLoading = false,
}: ScholarshipRuleModalProps) {
  const getAvailableFields = (ruleType: string) => {
    switch (ruleType) {
      case "student":
        return STUDENT_FIELDS;
      case "student_term":
        return STUDENT_TERM_FIELDS;
      default:
        return [];
    }
  };
  const [formData, setFormData] = useState<Partial<ScholarshipRule>>({
    rule_name: "",
    rule_type: "",
    tag: "",
    description: "",
    condition_field: "",
    operator: "==",
    expected_value: "",
    message: "",
    message_en: "",
    is_hard_rule: false,
    is_warning: false,
    priority: 1,
    is_active: true,
    is_initial_enabled: true,
    is_renewal_enabled: true,
    sub_type: undefined,
    academic_year: academicYear,
    semester: semester ?? undefined,
    is_template: false,
    template_name: undefined,
    template_description: undefined,
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [subTypeOptions, setSubTypeOptions] = useState<SubTypeOption[]>([
    { value: null, label: "通用", label_en: "General", is_default: true },
  ]);
  const [loadingSubTypes, setLoadingSubTypes] = useState(false);

  useEffect(() => {
    if (rule) {
      setFormData({
        rule_name: rule.rule_name,
        rule_type: rule.rule_type,
        tag: rule.tag || "",
        description: rule.description || "",
        condition_field: rule.condition_field,
        operator: rule.operator,
        expected_value: rule.expected_value,
        message: rule.message || "",
        message_en: rule.message_en || "",
        is_hard_rule: rule.is_hard_rule,
        is_warning: rule.is_warning,
        priority: rule.priority,
        is_active: rule.is_active,
        is_initial_enabled: rule.is_initial_enabled,
        is_renewal_enabled: rule.is_renewal_enabled,
        sub_type: rule.sub_type ?? undefined,
        academic_year: rule.academic_year || academicYear,
        semester: rule.semester ?? semester ?? undefined,
        is_template: rule.is_template,
        template_name: rule.template_name ?? undefined,
        template_description: rule.template_description ?? undefined,
      });
    } else {
      setFormData({
        rule_name: "",
        rule_type: "",
        tag: "",
        description: "",
        condition_field: "",
        operator: "==",
        expected_value: "",
        message: "",
        message_en: "",
        is_hard_rule: false,
        is_warning: false,
        priority: 1,
        is_active: true,
        is_initial_enabled: true,
        is_renewal_enabled: true,
        sub_type: undefined,
        academic_year: academicYear,
        semester: semester ?? undefined,
        is_template: false,
        template_name: undefined,
        template_description: undefined,
      });
    }
    setErrors({});
  }, [rule, academicYear, semester]);

  // Load sub-type options when modal opens
  useEffect(() => {
    const loadSubTypes = async () => {
      if (!isOpen || !scholarshipTypeId) {
        // Reset to default options when modal closes or no scholarship type
        setSubTypeOptions([
          { value: null, label: "通用", label_en: "General", is_default: true },
        ]);
        return;
      }

      setLoadingSubTypes(true);
      try {
        const response =
          await api.admin.getScholarshipRuleSubTypes(scholarshipTypeId);
        if (response.success && response.data && Array.isArray(response.data)) {
          setSubTypeOptions(response.data);
        } else {
          console.error("Failed to load sub-types:", response.message);
          // Keep default options on error
          setSubTypeOptions([
            {
              value: null,
              label: "通用",
              label_en: "General",
              is_default: true,
            },
          ]);
        }
      } catch (error) {
        console.error("Error loading sub-types:", error);
        // Keep default options on error
        setSubTypeOptions([
          { value: null, label: "通用", label_en: "General", is_default: true },
        ]);
      } finally {
        setLoadingSubTypes(false);
      }
    };

    loadSubTypes();
  }, [isOpen, scholarshipTypeId]);

  const handleChange = (field: keyof ScholarshipRule, value: any) => {
    setFormData(prev => {
      const newData = { ...prev, [field]: value };

      // 當規則類型改變時，清空條件欄位
      if (field === "rule_type" && prev.rule_type !== value) {
        newData.condition_field = "";
      }

      return newData;
    });
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: "" }));
    }
  };

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.rule_name?.trim()) {
      newErrors.rule_name = "規則名稱為必填項目";
    }
    if (!formData.rule_type?.trim()) {
      newErrors.rule_type = "規則類型為必填項目";
    }
    if (!formData.condition_field?.trim()) {
      newErrors.condition_field = "條件欄位為必填項目";
    }
    if (!formData.operator?.trim()) {
      newErrors.operator = "運算子為必填項目";
    }
    if (!formData.expected_value?.trim()) {
      newErrors.expected_value = "期望值為必填項目";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validateForm()) return;

    try {
      const submitData = {
        ...formData,
        scholarship_type_id: scholarshipTypeId,
      };
      await onSubmit(submitData);
      onClose();
    } catch (error) {
      console.error("提交規則失敗:", error);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={rule ? "編輯審核規則" : "新增審核規則"}
      size="xl"
    >
      <div className="space-y-6 max-h-[70vh] overflow-y-auto p-2">
        {/* 基本資訊 */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>規則名稱 *</Label>
            <Input
              value={formData.rule_name || ""}
              onChange={e => handleChange("rule_name", e.target.value)}
              placeholder="輸入規則名稱"
              className={errors.rule_name ? "border-red-500" : ""}
            />
            {errors.rule_name && (
              <p className="text-sm text-red-500">{errors.rule_name}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label>規則類型 *</Label>
            <Select
              value={formData.rule_type || ""}
              onValueChange={value => handleChange("rule_type", value)}
            >
              <SelectTrigger
                className={errors.rule_type ? "border-red-500" : ""}
              >
                <SelectValue placeholder="選擇規則類型" />
              </SelectTrigger>
              <SelectContent>
                {RULE_TYPES.map(type => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.rule_type && (
              <p className="text-sm text-red-500">{errors.rule_type}</p>
            )}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div className="space-y-2">
            <Label>標籤</Label>
            <Input
              value={formData.tag || ""}
              onChange={e => handleChange("tag", e.target.value)}
              placeholder="例：博士生、中華民國國籍"
            />
          </div>
          <div className="space-y-2">
            <Label>子類型</Label>
            <Select
              value={formData.sub_type || "__general__"}
              onValueChange={value =>
                handleChange("sub_type", value === "__general__" ? null : value)
              }
              disabled={loadingSubTypes}
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={loadingSubTypes ? "載入中..." : "選擇子類型"}
                />
              </SelectTrigger>
              <SelectContent>
                {subTypeOptions.map(option => (
                  <SelectItem
                    key={option.value || "__general__"}
                    value={option.value || "__general__"}
                  >
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>優先級</Label>
            <Input
              type="number"
              min="1"
              max="999"
              value={formData.priority || 1}
              onChange={e =>
                handleChange("priority", parseInt(e.target.value) || 1)
              }
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label>規則描述</Label>
          <Textarea
            value={formData.description || ""}
            onChange={e => handleChange("description", e.target.value)}
            placeholder="輸入規則描述"
            rows={2}
          />
        </div>

        {/* 條件設定 */}
        <div className="space-y-4">
          <h4 className="font-semibold text-lg">條件設定</h4>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label>條件欄位 *</Label>
              <Select
                value={formData.condition_field || ""}
                onValueChange={value => handleChange("condition_field", value)}
              >
                <SelectTrigger
                  className={errors.condition_field ? "border-red-500" : ""}
                >
                  <SelectValue placeholder="選擇欄位" />
                </SelectTrigger>
                <SelectContent>
                  {getAvailableFields(formData.rule_type || "").map(field => (
                    <SelectItem key={field.value} value={field.value}>
                      {field.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.condition_field && (
                <p className="text-sm text-red-500">{errors.condition_field}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label>運算子 *</Label>
              <Select
                value={formData.operator || "=="}
                onValueChange={value => handleChange("operator", value)}
              >
                <SelectTrigger
                  className={errors.operator ? "border-red-500" : ""}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OPERATORS.map(op => (
                    <SelectItem key={op.value} value={op.value}>
                      {op.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.operator && (
                <p className="text-sm text-red-500">{errors.operator}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label>期望值 *</Label>
              <Input
                value={formData.expected_value || ""}
                onChange={e => handleChange("expected_value", e.target.value)}
                placeholder="例：1, 1,2,3, 中華民國"
                className={errors.expected_value ? "border-red-500" : ""}
              />
              {errors.expected_value && (
                <p className="text-sm text-red-500">{errors.expected_value}</p>
              )}
            </div>
          </div>
        </div>

        {/* 驗證訊息 */}
        <div className="space-y-4">
          <h4 className="font-semibold text-lg">驗證訊息</h4>
          <div className="grid grid-cols-1 gap-4">
            <div className="space-y-2">
              <Label>中文訊息</Label>
              <Textarea
                value={formData.message || ""}
                onChange={e => handleChange("message", e.target.value)}
                placeholder="當規則不符合時顯示的中文訊息"
                rows={2}
              />
            </div>
            <div className="space-y-2">
              <Label>英文訊息</Label>
              <Textarea
                value={formData.message_en || ""}
                onChange={e => handleChange("message_en", e.target.value)}
                placeholder="當規則不符合時顯示的英文訊息"
                rows={2}
              />
            </div>
          </div>
        </div>

        {/* 規則設定 */}
        <div className="space-y-4">
          <h4 className="font-semibold text-lg">規則設定</h4>
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm font-medium">硬性規則</Label>
                  <p className="text-xs text-muted-foreground">
                    必須滿足，否則不會顯示在學生頁面
                  </p>
                </div>
                <Switch
                  checked={formData.is_hard_rule || false}
                  onCheckedChange={checked =>
                    handleChange("is_hard_rule", checked)
                  }
                />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm font-medium">警告規則</Label>
                  <p className="text-xs text-muted-foreground">
                    不符合時顯示警告
                  </p>
                </div>
                <Switch
                  checked={formData.is_warning || false}
                  onCheckedChange={checked =>
                    handleChange("is_warning", checked)
                  }
                />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm font-medium">規則啟用</Label>
                  <p className="text-xs text-muted-foreground">
                    整體規則是否啟用
                  </p>
                </div>
                <Switch
                  checked={formData.is_active || false}
                  onCheckedChange={checked =>
                    handleChange("is_active", checked)
                  }
                />
              </div>
            </div>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm font-medium">初領適用</Label>
                  <p className="text-xs text-muted-foreground">
                    是否適用於初次申請
                  </p>
                </div>
                <Switch
                  checked={formData.is_initial_enabled || false}
                  onCheckedChange={checked =>
                    handleChange("is_initial_enabled", checked)
                  }
                  className="data-[state=checked]:bg-blue-500"
                />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm font-medium">續領適用</Label>
                  <p className="text-xs text-muted-foreground">
                    是否適用於續領申請
                  </p>
                </div>
                <Switch
                  checked={formData.is_renewal_enabled || false}
                  onCheckedChange={checked =>
                    handleChange("is_renewal_enabled", checked)
                  }
                  className="data-[state=checked]:bg-orange-500"
                />
              </div>
            </div>
          </div>
        </div>

        {/* 規則屬性預覽 */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">規則屬性預覽</Label>
          <div className="flex flex-wrap gap-2">
            {formData.is_hard_rule && (
              <Badge variant="destructive" className="text-xs">
                必要規則
              </Badge>
            )}
            {formData.is_warning && (
              <Badge variant="outline" className="text-xs">
                警告規則
              </Badge>
            )}
            {formData.is_active ? (
              <Badge variant="default" className="text-xs">
                已啟用
              </Badge>
            ) : (
              <Badge variant="secondary" className="text-xs">
                已停用
              </Badge>
            )}
            {formData.is_initial_enabled && (
              <Badge className="text-xs bg-blue-500">初領適用</Badge>
            )}
            {formData.is_renewal_enabled && (
              <Badge className="text-xs bg-orange-500">續領適用</Badge>
            )}
          </div>
        </div>
      </div>

      {/* 操作按鈕 */}
      <div className="flex justify-end gap-2 pt-4 border-t">
        <Button variant="outline" onClick={onClose} disabled={isLoading}>
          <X className="h-4 w-4 mr-1" />
          取消
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={isLoading}
          className="nycu-gradient text-white"
        >
          <Save className="h-4 w-4 mr-1" />
          {isLoading ? "處理中..." : rule ? "更新規則" : "建立規則"}
        </Button>
      </div>
    </Modal>
  );
}
