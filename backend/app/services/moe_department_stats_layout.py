"""Fixed row layout of 統計教育部博士生獎學金-各系所獲獎生人數.

The office's reference form (各系所屬於哪個領域-只統計教育部獲獎生) lists each
department under its 教育部統計處大專校院學科標準分類 field, in this order.
Rows are matched by department **name** (``departments.name`` for the
student's ``std_depno``), not code: one 系所 carries several SIS codes (one per
degree / campus — e.g. 教育研究所 is 148, 248, 3460 and 4460), and the form
names the 系所, not a code.

Each row is ``(row label, names that count in that row)``. The label is the
name printed on the form; extra names are the SIS spellings of the same 系所.
"""

from typing import FrozenSet, Tuple

DepartmentRow = Tuple[str, FrozenSet[str]]
FieldGroup = Tuple[str, Tuple[DepartmentRow, ...]]


def _row(label: str, *aliases: str) -> DepartmentRow:
    return (label, frozenset({label, *aliases}))


MOE_DEPARTMENT_FIELD_LAYOUT: Tuple[FieldGroup, ...] = (
    ("01教育", (_row("教育研究所"),)),
    (
        "02藝術及人文領域",
        (
            _row("客家文化學院博士班"),
            _row("應用藝術研究所"),
            _row("社會與文化研究所"),
        ),
    ),
    (
        "04商業、管理及法律領域",
        (
            _row("資訊管理與財務金融學系"),
            _row("科技管理研究所"),
            _row("經營管理研究所"),
            _row("科技法律研究所"),
            _row("管理科學系"),
        ),
    ),
    (
        "05自然科學、數學及統計領域",
        (
            _row("生物科技學系"),
            _row("生物資訊及系統生物研究所"),
            _row("分子醫學與生物工程研究所"),
            _row("生醫科學與工程博士學位學程"),
            # SIS appends the 台灣聯合大學系統 qualifier (with and without a space).
            _row("跨領域神經科學博士學位學程", "跨領域神經科學博士學位學程(台灣聯合大學系統)"),
            _row("生物醫學影像暨放射科學系"),
            _row("生物醫學暨工程科技產業博士學位學程"),
            _row("生命科學系暨基因體科學研究所"),
            _row("神經科學研究所"),
            _row("微生物及免疫學研究所"),
            _row("生化暨分子生物研究所"),
            _row("分子醫學博士學位學程"),
            _row("生技醫療產業博士學位學程"),
            _row("電子物理學系"),
            _row("應用數學系"),
            _row("應用化學系"),
            _row("統計學研究所"),
            _row("物理研究所"),
            _row("工程生物科學學院產業博士班"),
            _row("生物醫學資訊研究所"),
        ),
    ),
    (
        "06資訊通訊科技",
        (
            _row("資訊科學與工程研究所"),
            _row("智慧科學暨綠能學院博士班"),
            _row("資訊管理研究所"),
            _row("智能系統研究所"),
        ),
    ),
    (
        "07工程、製造及營建領域",
        (
            _row("生物醫學工程學系"),
            _row("生醫光電研究所"),
            _row("工業工程與管理學系"),
            _row("機械工程學系"),
            _row("土木工程學系"),
            _row("材料科學與工程學系"),
            _row("環境工程研究所"),
            _row("電機工程學系"),
            _row("電子研究所"),
            _row("電控工程研究所"),
            _row("電信工程研究所"),
            _row("光電工程學系"),
            _row("電機學院博士班"),
            _row("光電學院博士班"),
            _row("國際半導體產業學院"),
            _row("前瞻半導體研究所"),
        ),
    ),
    (
        "09醫藥衛生及社會福利領域",
        (
            _row("醫學生物技術暨檢驗學系"),
            _row("物理治療暨輔助科技學系"),
            _row("牙醫學系"),
            _row("口腔生物研究所"),
            _row("藥理學研究所"),
            # The reference form prints 「環境與職業衛生生化暨分子生物研究所研究所」, a
            # paste slip of this 所's name; SIS has 環境與職業衛生研究所 (3110/4110).
            _row("環境與職業衛生研究所", "環境與職業衛生生化暨分子生物研究所研究所"),
            _row("生物藥學研究所"),
            _row("醫藥品法規科學博士學位學程"),
            _row("護理學系"),
            _row("臨床護理研究所"),
            _row("急重症醫學研究所"),
            _row("腦科學研究所"),
            _row("跨領域醫學博士學位學程"),
            _row("臨床醫學研究所"),
            _row("生理學研究所"),
            _row("公共衛生研究所"),
        ),
    ),
)
