
不需要存學期資料了 之後會由 API 或是 學校的學籍資料庫取得 


    id = Column(Integer, primary_key=True, index=True)
    
    # 學籍資料
    std_stdno = Column(String(20), unique=True, index=True, nullable=True)  # 學號代碼 (目前不知道用途 先保留)
    std_stdcode = Column(String(20), unique=True, index=True, nullable=False)  # 學號 (nycu_id)
    std_pid = Column(String(20), nullable=True)  # 身分證字號
    std_cname = Column(String(50), nullable=False)  # 中文姓名
    std_ename = Column(String(50), nullable=False)  # 英文姓名
    std_degree = Column(String(1), nullable=False)  # 攻讀學位：1:博士, 2:碩士, 3:學士
    std_studingstatus = Column(String(1), nullable=True)  # 在學狀態
    std_sex = Column(String(1), nullable=True)  # 性別: 1:男, 2:女
    std_enrollyear = Column(String(4), nullable=True)  # 入學學年度 (民國年)
    std_enrollterm = Column(String(1), nullable=True)  # 入學學期 (第一或第二)
    std_termcount = Column(Integer, nullable=True)  # 在學學期數

    # 國籍與身份
    std_nation = Column(String(20), nullable=True)    # 1: 中華民國 2: 其他
    std_schoolid = Column(String(10), nullable=True)  # 在學身份 (數字代碼)
    std_identity = Column(String(20), nullable=True)  # 陸生、僑生、外籍生等

    # 系所與學院
    std_depno = Column(String(20), nullable=True)  # 系所代碼
    std_depname = Column(String(100), nullable=True)  # 系所名稱
    std_aca_no = Column(String(20), nullable=True)  # 學院代碼
    std_aca_cname = Column(String(100), nullable=True)  # 學院名稱

    # 學歷背景
    std_highestschname = Column(String(100), nullable=True)  # 原就讀系所／畢業學校
    
    # 聯絡資訊
    com_cellphone = Column(String(20), nullable=True)
    com_email = Column(String(100), nullable=True)
    com_commzip = Column(String(10), nullable=True)
    com_commadd = Column(String(200), nullable=True)

    # 入學日期（可由 enrollyear + term 推算）
    std_enrolled_date = Column(Date, nullable=True)

    # 匯款資訊
    std_bank_account = Column(String(50), nullable=True)

    # 其他備註
    notes = Column(String(255), nullable=True)
