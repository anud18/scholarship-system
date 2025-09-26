"use client"

import React, { useState } from 'react'
import { Edit, Save, X, Trash2, Plus } from 'lucide-react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Modal } from './ui/modal'
import { UserListResponse, UserCreate } from '@/lib/api'
import { Badge } from './ui/badge'

interface UserEditModalProps {
  isOpen: boolean
  onClose: () => void
  editingUser: UserListResponse | null
  userForm: UserCreate
  onUserFormChange: (field: keyof UserCreate, value: any) => void
  onSubmit: () => void
  isLoading?: boolean
  // 獎學金權限相關
  scholarshipPermissions?: any[]
  availableScholarships?: Array<{ id: number; name: string; name_en?: string; code: string }>
  onPermissionChange?: (permissions: any[]) => void
}

export function UserEditModal({
  isOpen,
  onClose,
  editingUser,
  userForm,
  onUserFormChange,
  onSubmit,
  isLoading = false,
  scholarshipPermissions = [],
  availableScholarships = [],
  onPermissionChange
}: UserEditModalProps) {
  const isEditing = !!editingUser

  // 獎學金權限相關狀態
  const [selectedScholarshipIds, setSelectedScholarshipIds] = useState<number[]>([])

  // 初始化已選擇的獎學金 ID
  React.useEffect(() => {
    if (scholarshipPermissions.length > 0 && editingUser?.id) {
      // 只顯示當前編輯用戶的權限
      const userPermissions = scholarshipPermissions.filter(p => p.user_id === Number(editingUser.id))
      const selectedIds = userPermissions.map(p => p.scholarship_id)
      setSelectedScholarshipIds(selectedIds)
    } else {
      setSelectedScholarshipIds([])
    }
  }, [scholarshipPermissions, editingUser?.id])

  // 當角色改變時，清除獎學金權限
  React.useEffect(() => {
    if (!['college', 'admin', 'super_admin'].includes(userForm.role)) {
      setSelectedScholarshipIds([])
      // 通知父組件清除權限
      onPermissionChange?.([])
    }
  }, [userForm.role]) // 移除 onPermissionChange 依賴

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? '編輯使用者權限' : '新增使用者權限'}
      size="lg"
    >
      <div className="space-y-4">
        {isEditing ? (
          // 編輯模式：顯示用戶信息（唯讀）
          <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div>
                <Label className="text-sm font-medium text-gray-600">NYCU ID</Label>
                <p className="text-sm text-gray-900">{userForm.nycu_id}</p>
              </div>
              <div>
                <Label className="text-sm font-medium text-gray-600">電子郵件</Label>
                <p className="text-sm text-gray-900">{userForm.email}</p>
              </div>
            </div>
            <div>
              <Label className="text-sm font-medium text-gray-600">姓名</Label>
              <p className="text-sm text-gray-900">{userForm.name}</p>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div>
                <Label className="text-sm font-medium text-gray-600">用戶類型</Label>
                <p className="text-sm text-gray-900">{userForm.user_type || 'student'}</p>
              </div>
              <div>
                <Label className="text-sm font-medium text-gray-600">狀態</Label>
                <p className="text-sm text-gray-900">{userForm.status || '在學'}</p>
              </div>
            </div>
            <div className="text-xs text-gray-500">
              * 以上信息由 SSO 系統管理，無法在此處修改
            </div>
          </div>
        ) : (
          // 新增模式：只需要 NYCU ID
          <div className="space-y-4 p-4 bg-blue-50 rounded-lg">
            <div className="space-y-2">
              <Label>NYCU ID *</Label>
              <Input
                value={userForm.nycu_id || ''}
                onChange={(e) => onUserFormChange('nycu_id', e.target.value)}
                placeholder="請輸入 NYCU ID"
                className="border-nycu-blue-200"
              />
              <p className="text-xs text-gray-500">
                * 其他用戶信息將在用戶首次登入時從 SSO 系統自動獲取
              </p>
            </div>
          </div>
        )}

        {/* 權限設置區域 */}
        <div className="border-t pt-4">
          <h3 className="text-lg font-medium mb-4">權限設置</h3>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label>角色 *</Label>
              <select
                value={userForm.role}
                onChange={(e) => onUserFormChange('role', e.target.value)}
                className="w-full px-3 py-2 border border-nycu-blue-200 rounded-md"
              >
                <option value="">請選擇角色</option>
                <option value="professor">教授</option>
                <option value="college">學院</option>
                <option value="admin">管理員</option>
                <option value="super_admin">超級管理員</option>
              </select>
              <p className="text-xs text-gray-500">
                角色決定用戶在系統中的權限範圍
              </p>
            </div>

            <div className="space-y-2">
              <Label>備註</Label>
              <Input
                value={userForm.comment || ''}
                onChange={(e) => onUserFormChange('comment', e.target.value)}
                placeholder="管理員備註（可選）"
                className="border-nycu-blue-200"
              />
              <p className="text-xs text-gray-500">
                用於記錄特殊權限或管理說明
              </p>
            </div>
          </div>
        </div>

        {/* super_admin 自動擁有所有權限的說明 */}
        {isEditing && userForm.role === 'super_admin' && (
          <div className="border-t pt-4">
            <div className="p-4 bg-green-50 rounded-lg border border-green-200">
              <h3 className="text-lg font-medium mb-2 text-green-800">超級管理員權限</h3>
              <p className="text-sm text-green-700">
                超級管理員自動擁有所有獎學金的完整管理權限，無需額外設定。
              </p>
            </div>
          </div>
        )}

        {/* 獎學金權限設置區域 - 只有管理角色需要設定 */}
        {isEditing && ['college', 'admin', 'super_admin'].includes(userForm.role) && (
          <div className="border-t pt-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-1.5 h-1.5 bg-blue-500 rounded-full"></div>
              <h3 className="text-lg font-semibold text-gray-900">獎學金管理權限設置</h3>
            </div>

            {/* 獎學金選擇區域 */}
            <div className="space-y-6">
              {/* 選擇器區域 */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-sm font-medium text-gray-700">選擇獎學金管理權限</Label>
                  <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
                    {selectedScholarshipIds.length} / {availableScholarships.length}
                  </span>
                </div>

                <div className="relative group">
                  <div className="border border-gray-200 rounded-lg bg-white shadow-sm group-hover:border-gray-300 group-focus-within:border-blue-500 group-focus-within:ring-1 group-focus-within:ring-blue-500 transition-all duration-200">
                    <select
                      multiple
                      value={selectedScholarshipIds.map(String)}
                      onChange={(e) => {
                        const selectedOptions = Array.from(e.target.selectedOptions, option => parseInt(option.value))

                        // 立即更新狀態
                        setSelectedScholarshipIds(selectedOptions)

                        // 簡化的權限更新邏輯
                        const newPermissions = []

                        for (const scholarshipId of selectedOptions) {
                          const scholarship = availableScholarships.find(s => s.id === scholarshipId)
                          if (!scholarship) continue

                          // 檢查是否已存在此權限（保留現有權限的 ID）
                          const existingPermission = scholarshipPermissions.find(p => p.scholarship_id === scholarshipId && p.user_id === Number(editingUser?.id))

                          if (existingPermission) {
                            // 保留現有權限（包括 ID）
                            newPermissions.push(existingPermission)
                          } else {
                            // 創建新權限（使用臨時 ID）
                            newPermissions.push({
                              id: Date.now() + Math.random(),
                              user_id: editingUser?.id ? Number(editingUser.id) : -1,
                              scholarship_id: scholarship.id,
                              scholarship_name: scholarship.name,
                              scholarship_name_en: scholarship.name_en,
                              comment: ''
                            })
                          }
                        }

                        onPermissionChange?.(newPermissions)
                      }}
                      className="w-full px-4 py-3 text-sm border-0 focus:ring-0 focus:outline-none min-h-[140px] bg-transparent resize-none"
                    >
                      {availableScholarships.map((scholarship) => (
                        <option
                          key={scholarship.id}
                          value={scholarship.id}
                          className="px-4 py-2 hover:bg-gray-50"
                        >
                          {scholarship.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="mt-3 flex items-center gap-3 text-xs text-gray-500">
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-full">
                      <div className="w-1.5 h-1.5 bg-blue-500 rounded-full"></div>
                      <span>按住 Ctrl (Windows) 或 Cmd (Mac) 可多選</span>
                    </div>
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-full">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span>可選擇多個獎學金</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* 已選擇的獎學金顯示 */}
              {(() => {
                // 只顯示當前編輯用戶的權限
                const userPermissions = editingUser?.id
                  ? scholarshipPermissions.filter(p => p.user_id === Number(editingUser.id))
                  : scholarshipPermissions.filter(p => p.user_id === -1) // 新用戶的臨時權限

                if (userPermissions.length > 0) {
                  return (
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <Label className="text-sm font-medium text-gray-700">已選擇的獎學金</Label>
                        <div className="flex items-center gap-1 px-2 py-0.5 bg-green-50 border border-green-200 rounded-full">
                          <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
                          <span className="text-xs text-green-700 font-medium">{userPermissions.length} 個</span>
                        </div>
                      </div>

                      <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl p-4 border border-gray-200 shadow-sm">
                        <div className="flex flex-wrap gap-2">
                          {userPermissions.map((permission, index) => (
                            <div
                              key={permission.id}
                              className="inline-flex items-center gap-2 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 shadow-sm hover:border-blue-300 hover:shadow-md transition-all duration-200 group"
                            >
                              <div className="w-2 h-2 bg-blue-500 rounded-full group-hover:bg-blue-600 transition-colors"></div>
                              <span>{permission.scholarship_name}</span>
                              <div className="w-4 h-4 bg-gray-100 rounded-full flex items-center justify-center text-xs text-gray-500 font-bold">
                                {index + 1}
                              </div>
                            </div>
                          ))}
                        </div>

                        <div className="mt-4 pt-3 border-t border-gray-200">
                          <div className="flex items-center justify-between">
                            <p className="text-xs text-gray-500">
                              總計選擇了 <span className="font-semibold text-gray-700">{userPermissions.length}</span> 個獎學金管理權限
                            </p>
                            <div className="flex items-center gap-1 text-xs text-gray-400">
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                              </svg>
                              <span>權限已設定</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                } else {
                  return (
                    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl p-8 border border-gray-200">
                      <div className="text-center">
                        <div className="w-16 h-16 bg-gray-200 rounded-full flex items-center justify-center mx-auto mb-4">
                          <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                        </div>
                        <h4 className="text-sm font-medium text-gray-700 mb-2">尚未選擇任何獎學金</h4>
                        <p className="text-xs text-gray-500 max-w-sm mx-auto">
                          請從上方下拉選單中選擇要管理的獎學金。選擇後，該用戶將擁有對應獎學金的完整管理權限。
                        </p>
                      </div>
                    </div>
                  )
                }
              })()}
            </div>
          </div>
        )}

        {/* 教授角色說明 */}
        {isEditing && userForm.role === 'professor' && (
          <div className="border-t pt-6">
            <div className="p-4 bg-amber-50 rounded-lg border border-amber-200">
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <h3 className="text-sm font-medium text-amber-800">教授角色說明</h3>
              </div>
              <p className="text-sm text-amber-700">
                教授角色主要用於審核學生申請，無需設定獎學金管理權限。如需管理獎學金，請將角色更改為學院、管理員或超級管理員。
              </p>
            </div>
          </div>
        )}

        <div className="flex gap-2 pt-4">
          <Button
            onClick={onSubmit}
            disabled={isLoading || !userForm.nycu_id || !userForm.role}
            className="nycu-gradient text-white"
          >
            <Save className="h-4 w-4 mr-1" />
            {isLoading ? '處理中...' : (isEditing ? '更新權限' : '建立權限')}
          </Button>
          <Button variant="outline" onClick={onClose}>
            <X className="h-4 w-4 mr-1" />
            取消
          </Button>
        </div>
      </div>
    </Modal>
  )
}
