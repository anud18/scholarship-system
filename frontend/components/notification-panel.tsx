"use client"

import { useState, useEffect } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Bell,
  AlertCircle,
  Info,
  AlertTriangle,
  CheckCircle,
  Clock,
  ExternalLink,
  ChevronDown,
  ChevronUp
} from "lucide-react"
import { format } from "date-fns"
import { zhCN, enUS } from "date-fns/locale"
import { apiClient } from "@/lib/api"

interface NotificationData {
  id: number
  title: string
  title_en?: string
  message: string
  message_en?: string
  notification_type: "info" | "warning" | "error" | "success" | "reminder"
  priority: "low" | "normal" | "high" | "urgent"
  related_resource_type?: string
  related_resource_id?: number
  action_url?: string
  is_read: boolean
  is_dismissed: boolean
  scheduled_at?: string
  expires_at?: string
  read_at?: string
  created_at: string
  metadata?: any
}

interface NotificationPanelProps {
  locale: "zh" | "en"
  onNotificationClick?: (notification: NotificationData) => void
  onMarkAsRead?: (notificationId: number) => void
  onMarkAllAsRead?: () => void
}

export function NotificationPanel({
  locale = "zh",
  onNotificationClick,
  onMarkAsRead,
  onMarkAllAsRead
}: NotificationPanelProps) {
  const [notifications, setNotifications] = useState<NotificationData[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedNotifications, setExpandedNotifications] = useState<Set<number>>(new Set())

  // 獲取通知列表
  const fetchNotifications = async () => {
    try {
      setIsLoading(true)
      setError(null)

      const response = await apiClient.notifications.getNotifications(0, 50)
      if (response.success) {
        const notifications = (response.data || []).map(n => ({
          ...n,
          notification_type: n.notification_type as "info" | "warning" | "error" | "success" | "reminder",
          priority: n.priority as "low" | "normal" | "high" | "urgent"
        }))
        setNotifications(notifications)
      } else {
        throw new Error(response.message || '獲取通知失敗')
      }
    } catch (err) {
      console.error('獲取通知錯誤:', err)
      setError(err instanceof Error ? err.message : '獲取通知失敗')
    } finally {
      setIsLoading(false)
    }
  }

  // 獲取未讀通知數量
  const fetchUnreadCount = async () => {
    try {
      const response = await apiClient.notifications.getUnreadCount()
      if (response.success) {
        setUnreadCount(response.data || 0)
      }
    } catch (err) {
      console.error('獲取未讀通知數量錯誤:', err)
    }
  }

  // 標記通知為已讀
  const handleMarkAsRead = async (notificationId: number) => {
    try {
      const response = await apiClient.notifications.markAsRead(notificationId)
      if (response.success) {
        // 更新本地狀態
        setNotifications(prev =>
          prev.map(n =>
            n.id === notificationId
              ? { ...n, is_read: true, read_at: new Date().toISOString() }
              : n
          )
        )
        fetchUnreadCount()
        onMarkAsRead?.(notificationId)
      }
    } catch (err) {
      console.error('標記已讀失敗:', err)
    }
  }

  // 自動標記所有通知為已讀（當用戶查看通知面板時）
  const autoMarkAllAsRead = async () => {
    try {
      const response = await apiClient.notifications.markAllAsRead()
      if (response.success) {
        // 更新本地狀態
        setNotifications(prev =>
          prev.map(n => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
        )
        setUnreadCount(0)
        onMarkAllAsRead?.()
      }
    } catch (err) {
      console.error('自動標記全部已讀失敗:', err)
    }
  }

  // 切換通知展開狀態
  const toggleNotificationExpanded = (notificationId: number) => {
    setExpandedNotifications(prev => {
      const newSet = new Set(prev)
      if (newSet.has(notificationId)) {
        newSet.delete(notificationId)
      } else {
        newSet.add(notificationId)
      }
      return newSet
    })
  }

  // 檢查訊息是否過長需要展開功能
  const isMessageLong = (message: string) => {
    return message.length > 80 // 如果訊息超過80個字符，認為是長訊息
  }

  // 獲取通知類型圖標
  const getNotificationIcon = (type: string, priority: string) => {
    const iconClass = priority === "urgent" ? "text-red-500" :
                     priority === "high" ? "text-orange-500" :
                     "text-blue-500"

    switch (type) {
      case "error":
        return <AlertCircle className={`h-4 w-4 ${iconClass}`} />
      case "warning":
        return <AlertTriangle className={`h-4 w-4 ${iconClass}`} />
      case "success":
        return <CheckCircle className={`h-4 w-4 ${iconClass}`} />
      case "reminder":
        return <Clock className={`h-4 w-4 ${iconClass}`} />
      default:
        return <Info className={`h-4 w-4 ${iconClass}`} />
    }
  }

  // 獲取優先級標籤
  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case "urgent":
        return <Badge variant="destructive" className="text-xs">緊急</Badge>
      case "high":
        return <Badge variant="secondary" className="text-xs">高</Badge>
      case "normal":
        return <Badge variant="outline" className="text-xs">普通</Badge>
      default:
        return null
    }
  }

  // 格式化時間
  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return format(date, "MM/dd HH:mm", {
      locale: locale === "zh" ? zhCN : enUS
    })
  }

  // 獲取通知標題和內容
  const getNotificationText = (notification: NotificationData) => {
    const title = locale === "en" && notification.title_en
      ? notification.title_en
      : notification.title
    const message = locale === "en" && notification.message_en
      ? notification.message_en
      : notification.message
    return { title, message }
  }

  useEffect(() => {
    fetchNotifications()
    fetchUnreadCount()

    // 當組件首次載入時，自動標記所有通知為已讀
    autoMarkAllAsRead()

    // 每30秒刷新一次通知
    const interval = setInterval(() => {
      fetchNotifications()
      fetchUnreadCount()
    }, 30000)

    return () => clearInterval(interval)
  }, [])

  // 當通知面板變為可見時也自動標記已讀
  useEffect(() => {
    if (notifications.length > 0) {
      autoMarkAllAsRead()
    }
  }, [notifications.length])

  if (isLoading) {
    return (
      <Card className="w-96">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Bell className="h-4 w-4" />
              {locale === "zh" ? "通知" : "Notifications"}
            </CardTitle>
            <Skeleton className="h-4 w-8" />
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-3 w-3/4" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="w-96">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Bell className="h-4 w-4" />
            {locale === "zh" ? "通知" : "Notifications"}
          </CardTitle>
          {unreadCount > 0 && (
            <Badge variant="destructive" className="text-xs">
              {unreadCount}
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="p-0">
        {error ? (
          <div className="p-4 text-center text-red-500 text-sm">
            {error}
            <Button
              variant="outline"
              size="sm"
              onClick={fetchNotifications}
              className="mt-2 text-xs"
            >
              {locale === "zh" ? "重試" : "Retry"}
            </Button>
          </div>
        ) : notifications.length === 0 ? (
          <div className="p-4 text-center text-gray-500 text-sm">
            {locale === "zh" ? "暫無通知" : "No notifications"}
          </div>
        ) : (
          <ScrollArea className="h-96">
            <div className="space-y-1">
              {notifications.map((notification, index) => {
                const { title, message } = getNotificationText(notification)
                const isExpanded = expandedNotifications.has(notification.id)
                const needsExpansion = isMessageLong(message)

                return (
                  <div key={notification.id}>
                    <div
                      className={`p-4 hover:bg-gray-50 transition-colors ${
                        !notification.is_read ? "bg-blue-50 border-l-4 border-l-blue-500" : ""
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="flex-shrink-0 mt-0.5">
                          {getNotificationIcon(notification.notification_type, notification.priority)}
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-2 mb-2">
                            <h4 className="text-sm font-semibold text-gray-900 leading-tight">
                              {title}
                            </h4>
                            <div className="flex items-center gap-1 flex-shrink-0">
                              {getPriorityBadge(notification.priority)}
                              {!notification.is_read && (
                                <div className="w-2 h-2 bg-blue-500 rounded-full" />
                              )}
                            </div>
                          </div>

                          <div className="space-y-2">
                            <div
                              className={`text-sm text-gray-700 leading-relaxed ${
                                needsExpansion && !isExpanded ? "line-clamp-3" : ""
                              }`}
                            >
                              {message}
                            </div>

                            {needsExpansion && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  toggleNotificationExpanded(notification.id)
                                }}
                                className="h-6 px-2 text-xs text-blue-600 hover:text-blue-800 hover:bg-blue-50"
                              >
                                {isExpanded ? (
                                  <>
                                    <ChevronUp className="h-3 w-3 mr-1" />
                                    {locale === "zh" ? "收起" : "Collapse"}
                                  </>
                                ) : (
                                  <>
                                    <ChevronDown className="h-3 w-3 mr-1" />
                                    {locale === "zh" ? "展開" : "Expand"}
                                  </>
                                )}
                              </Button>
                            )}
                          </div>

                          <div className="flex items-center justify-between mt-3">
                            <span className="text-xs text-gray-500">
                              {formatDate(notification.created_at)}
                            </span>

                            <div className="flex items-center gap-2">
                              {notification.action_url && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="h-6 px-2 text-xs"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    if (notification.action_url) {
                                      // 自動標記為已讀
                                      if (!notification.is_read) {
                                        handleMarkAsRead(notification.id)
                                      }
                                      // 如果是相對路徑，使用內部導航；如果是絕對URL，在新標籤頁打開
                                      if (notification.action_url.startsWith('http')) {
                                        window.open(notification.action_url, '_blank')
                                      } else {
                                        window.location.href = notification.action_url
                                      }
                                    }
                                  }}
                                >
                                  <ExternalLink className="h-3 w-3 mr-1" />
                                  {locale === "zh" ? "查看" : "View"}
                                </Button>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                    {index < notifications.length - 1 && <Separator />}
                  </div>
                )
              })}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  )
}
