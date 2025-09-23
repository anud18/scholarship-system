#!/usr/bin/env python3
"""
測試 get_user_applications 修復：確保 ApplicationFile 記錄能正確顯示在前端
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set test environment
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///:memory:'
os.environ['TESTING'] = 'true'


async def test_get_applications_with_cloned_files():
    """測試 get_user_applications 能否正確返回 ApplicationFile 記錄"""
    
    from app.core.init_db import initDatabase
    from app.db.session import AsyncSessionLocal
    from app.models.application import Application, ApplicationFile
    from app.models.user import User
    from app.models.scholarship import SubTypeSelectionMode
    from app.services.application_service import ApplicationService
    from sqlalchemy import select
    
    print("🧪 測試 get_user_applications 修復")
    print("=" * 50)
    
    # 初始化資料庫
    await initDatabase()
    
    async with AsyncSessionLocal() as db:
        try:
            # 使用現有測試用戶
            stmt = select(User).where(User.nycu_id == "stu_under")
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                print("❌ 找不到測試用戶")
                return False
            
            print(f"✅ 使用測試用戶: {user.name} (ID: {user.id})")
            
            # 創建申請（手動，避免複雜的創建流程）
            application = Application(
                app_id=f"TEST-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                user_id=user.id,
                scholarship_type_id=1,
                scholarship_subtype_list=[],
                sub_type_selection_mode=SubTypeSelectionMode.SINGLE,
                status="draft",
                status_name="草稿",
                academic_year=114,
                student_data={  # 添加必要的學生資料
                    "std_stdcode": user.nycu_id,
                    "std_name": user.name
                },
                submitted_form_data={
                    "fields": {},
                    "documents": []  # 初始為空的 documents 陣列
                }
            )
            db.add(application)
            await db.commit()
            await db.refresh(application)
            
            print(f"✅ 申請已建立: {application.app_id}")
            print(f"📊 初始 submitted_form_data.documents: {len(application.submitted_form_data.get('documents', []))} 個文件")
            
            # 手動創建 ApplicationFile 記錄（模擬複製的銀行文件）
            application_file = ApplicationFile(
                application_id=application.id,
                file_type='bank_account_proof',
                filename='test_bank.jpg',
                original_filename='test_bank.jpg',
                file_size=12345,
                content_type="image/jpeg",
                object_name=f"applications/{application.app_id}/documents/test_bank.jpg",
                is_verified=True,
                uploaded_at=datetime.now(timezone.utc)
            )
            
            db.add(application_file)
            await db.commit()
            await db.refresh(application_file)
            
            print(f"✅ ApplicationFile 記錄已建立: ID={application_file.id}, file_type={application_file.file_type}")
            
            # 現在測試 get_user_applications 方法
            app_service = ApplicationService(db)
            applications = await app_service.get_user_applications(user, status=None)
            
            print(f"\n📋 get_user_applications 返回 {len(applications)} 個申請")
            
            if applications:
                app = applications[0]
                print(f"📄 申請: {app.app_id}")
                print(f"   Status: {app.status}")
                
                # 檢查 submitted_form_data.documents
                documents = app.submitted_form_data.get('documents', [])
                print(f"   📊 Documents 陣列長度: {len(documents)}")
                
                if documents:
                    print("   ✅ 成功！Documents 陣列包含文件:")
                    for i, doc in enumerate(documents, 1):
                        print(f"     📄 文件 {i}:")
                        print(f"       - document_type: {doc.get('document_type')}")
                        print(f"       - document_name: {doc.get('document_name')}")
                        print(f"       - file_id: {doc.get('file_id')}")
                        print(f"       - filename: {doc.get('filename')}")
                        print(f"       - is_verified: {doc.get('is_verified')}")
                        print(f"       - file_path: {doc.get('file_path')}")
                        
                        # 檢查前端映射所需的所有欄位
                        required_fields = ['file_id', 'document_type', 'filename', 'is_verified']
                        missing_fields = [f for f in required_fields if f not in doc or doc[f] is None]
                        
                        if missing_fields:
                            print(f"       ❌ 缺少必要欄位: {missing_fields}")
                            return False
                        else:
                            print("       ✅ 前端所需欄位完整")
                    
                    print("\n🎯 前端顯示模擬:")
                    print("   application-detail-dialog.tsx:178 會讀取 application.submitted_form_data.documents")
                    print("   轉換為 ApplicationFile 格式：")
                    for doc in documents:
                        frontend_file = {
                            'id': doc.get('file_id'),
                            'filename': doc.get('filename'),
                            'file_type': doc.get('document_type'),
                            'is_verified': doc.get('is_verified')
                        }
                        print(f"     前端文件: {frontend_file}")
                    
                    print("   ✅ 前端會顯示: 存摺封面*固定文件")
                    return True
                    
                else:
                    print("   ❌ Documents 陣列為空，前端會顯示 '尚未上傳任何文件'")
                    return False
            else:
                print("❌ get_user_applications 沒有返回任何申請")
                return False
                
        except Exception as e:
            print(f"❌ 測試過程中發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_get_applications_with_cloned_files())
    if success:
        print("\n🎉 修復成功！")
        print("✅ get_user_applications 現在會正確處理 ApplicationFile 記錄")
        print("✅ submitted_form_data.documents 會包含複製的固定文件")
        print("✅ 前端申請詳情對話框會顯示文件而不是 '尚未上傳任何文件'")
    else:
        print("\n❌ 修復失敗，需要進一步調試")
    sys.exit(0 if success else 1)