"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Building2 } from "lucide-react"

interface MatrixQuotaDisplayProps {
  quotas: Record<string, Record<string, number>> | null
  hasMatrix: boolean
}

export function MatrixQuotaDisplay({ quotas, hasMatrix }: MatrixQuotaDisplayProps) {
  if (!hasMatrix || !quotas || Object.keys(quotas).length === 0) {
    return null
  }

  // Extract unique colleges and sub_types
  const subTypes = Object.keys(quotas)
  const colleges = new Set<string>()

  subTypes.forEach(subType => {
    Object.keys(quotas[subType] || {}).forEach(college => {
      colleges.add(college)
    })
  })

  const collegeList = Array.from(colleges).sort()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Building2 className="h-5 w-5" />
          配額矩陣
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="font-semibold">子類型</TableHead>
              {collegeList.map((college) => (
                <TableHead key={college} className="text-center font-semibold">
                  {college} 學院
                </TableHead>
              ))}
              <TableHead className="text-center font-semibold">總計</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {subTypes.map((subType) => {
              const rowTotal = collegeList.reduce((sum, college) => {
                return sum + (quotas[subType]?.[college] || 0)
              }, 0)

              return (
                <TableRow key={subType}>
                  <TableCell className="font-medium">{subType}</TableCell>
                  {collegeList.map((college) => (
                    <TableCell key={college} className="text-center">
                      <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-primary/10 text-primary font-semibold">
                        {quotas[subType]?.[college] || 0}
                      </span>
                    </TableCell>
                  ))}
                  <TableCell className="text-center font-semibold text-primary">
                    {rowTotal}
                  </TableCell>
                </TableRow>
              )
            })}
            {/* Total row */}
            <TableRow className="bg-muted/50">
              <TableCell className="font-bold">總計</TableCell>
              {collegeList.map((college) => {
                const colTotal = subTypes.reduce((sum, subType) => {
                  return sum + (quotas[subType]?.[college] || 0)
                }, 0)
                return (
                  <TableCell key={college} className="text-center font-semibold">
                    {colTotal}
                  </TableCell>
                )
              })}
              <TableCell className="text-center font-bold text-primary text-lg">
                {subTypes.reduce((sum, subType) => {
                  return sum + collegeList.reduce((colSum, college) => {
                    return colSum + (quotas[subType]?.[college] || 0)
                  }, 0)
                }, 0)}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
