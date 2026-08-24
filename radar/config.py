"""Product scope and source-side filters."""

from collections import OrderedDict

CATEGORIES: OrderedDict[str, str] = OrderedDict(
    [
        ("产品", "🧭"),
        ("运营", "⚙️"),
        ("市场", "📣"),
        ("增长", "📈"),
        ("战略", "♟️"),
        ("商业分析", "📊"),
        ("销售", "💼"),
        ("商务", "🤝"),
        ("项目管理", "📋"),
        ("设计", "✦"),
        ("用户研究", "🔍"),
        ("职能", "🏢"),
    ]
)

CATEGORY_KEYWORDS: OrderedDict[str, tuple[str, ...]] = OrderedDict(
    [
        ("项目管理", ("项目管理", "项目经理", "program manager", "project manager", "项目pm")),
        (
            "增长",
            ("增长", "growth"),
        ),
        (
            "战略",
            (
                "战略",
                "行业研究",
                "产业研究",
                "生态研究",
                "投资",
                "strategy",
            ),
        ),
        (
            "商业分析",
            ("商业分析", "经营分析", "数据分析", "风险管理", "business analyst"),
        ),
        (
            "市场",
            (
                "市场",
                "营销",
                "品牌",
                "公关",
                "广告投放",
                "媒介",
                "marketing",
                "public relations",
                "pr",
            ),
        ),
        (
            "销售",
            (
                "销售",
                "客户成功",
                "渠道",
                "sales",
                "customer success",
            ),
        ),
        (
            "商务",
            (
                "商务",
                "商业化",
                "合作伙伴",
                "business development",
                "partnership",
                "解决方案",
                "bd",
            ),
        ),
        (
            "用户研究",
            ("用户研究", "user research"),
        ),
        (
            "设计",
            (
                "设计",
                "交互",
                "视觉",
                "美术",
                "动画",
                "特效",
                "音频策划",
                "creative",
                "designer",
                "ui",
                "ux",
            ),
        ),
        (
            "产品",
            (
                "产品经理",
                "产品策划",
                "产品实习",
                "游戏策划",
                "系统策划",
                "数值策划",
                "策划培训生",
                "项目实习生-产品",
                "product manager",
                "product management",
                "product intern",
            ),
        ),
        (
            "职能",
            (
                "人力",
                "招聘",
                "财务",
                "财经",
                "法务",
                "行政",
                "审计",
                "内审",
                "采购",
                "公共政策",
                "公共事务",
                "专利",
                "合规",
                "秘书",
                "接待管理",
                "设施设备管理",
                "资产管理",
                "项目实习生-职能",
                "hr",
                "finance",
                "legal",
                "recruiter",
            ),
        ),
        (
            "运营",
            (
                "运营",
                "内容",
                "编辑",
                "审核",
                "社区",
                "客服",
                "安全策略",
                "operations",
                "operation",
                "editor",
                "content",
            ),
        ),
    ]
)

BYTEDANCE_CATEGORY_IDS = [
    "6704215882479962371",  # 运营
    "6704215864629004552",  # 产品
    "6704215913488451847",  # 职能/支持
    "6709824272514156812",  # 设计
    "6709824272505768200",  # 销售
    "6704215901438216462",  # 市场
    "6850051244971526414",  # 游戏策划
]

TENCENT_POSITION_FAMILY_IDS = [
    79,
    80,
    83,
    94,
    219,
    253,
    85,
    89,
    78,
    82,
    96,
    192,
    326,
    327,
    328,
    329,
]

# A small denylist for technical roles occasionally filed under a non-engineering parent category.
TECHNICAL_TITLE_KEYWORDS = (
    "数据科学",
    "data scientist",
    "后端开发工程师",
    "前端开发工程师",
    "客户端开发工程师",
    "软件开发工程师",
    "算法工程师",
    "测试开发工程师",
    "研发工程师",
    "分析工程师",
    "ai agent开发",
    "ui开发",
    "计算语言学",
)
