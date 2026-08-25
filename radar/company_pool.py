"""Audited market-sector companies fetched through the pinned job-pro adapter package."""

from dataclasses import dataclass


@dataclass(frozen=True)
class JobProCompany:
    key: str
    company: str
    source: str
    hosts: tuple[str, ...]
    scopes: tuple[str, ...]
    early_only: bool = False


JOB_PRO_VERSION = "1.2.1"

APPROVED_COMPANIES = (
    JobProCompany("alibaba", "阿里巴巴", "阿里巴巴招聘", ("campus-talent.alibaba.com",), ("campus", "intern")),
    JobProCompany("antgroup", "蚂蚁集团", "蚂蚁集团招聘", ("talent.antgroup.com",), ("campus", "intern")),
    JobProCompany("baidu", "百度", "百度招聘", ("talent.baidu.com",), ("campus", "intern")),
    JobProCompany("bilibili", "哔哩哔哩", "哔哩哔哩招聘", ("jobs.bilibili.com",), ("campus", "intern")),
    JobProCompany("didi", "滴滴", "滴滴招聘", ("talent.didiglobal.com",), ("campus",)),
    JobProCompany("jd", "京东", "京东招聘", ("campus.jd.com",), ("campus", "intern")),
    JobProCompany("kuaishou", "快手", "快手招聘", ("campus.kuaishou.cn",), ("campus", "intern")),
    JobProCompany("meituan", "美团", "美团招聘", ("zhaopin.meituan.com",), ("campus", "intern")),
    JobProCompany("netease", "网易", "网易招聘", ("hr.163.com",), ("campus", "intern")),
    JobProCompany("pdd", "拼多多", "拼多多招聘", ("careers.pinduoduo.com",), ("campus", "intern")),
    JobProCompany("xiaohongshu", "小红书", "小红书招聘", ("job.xiaohongshu.com",), ("campus", "intern")),
    JobProCompany("huawei", "华为", "华为招聘", ("career.huawei.com",), ("campus", "intern")),
    JobProCompany("mihoyo", "米哈游", "米哈游招聘", ("jobs.mihoyo.com",), ("campus", "intern")),
    JobProCompany("trip", "携程", "携程招聘", ("careers.ctrip.com",), ("campus", "intern")),
    JobProCompany("oppo", "OPPO", "OPPO招聘", ("careers.oppo.com",), ("campus", "intern")),
    JobProCompany("vivo", "vivo", "vivo招聘", ("hr.vivo.com", "hr-campus.vivo.com"), ("campus", "intern")),
    JobProCompany("xiaomi", "小米", "小米招聘", ("xiaomi.jobs.f.mioffice.cn",), ("campus", "intern")),
    JobProCompany("minimax", "MiniMax", "MiniMax招聘", ("vrfi1sk8a0.jobs.feishu.cn",), ("campus", "intern")),
    JobProCompany("agibot", "智元机器人", "智元机器人招聘", ("agirobot.jobs.feishu.cn",), ("campus", "intern")),
    JobProCompany("horizonrobotics", "地平线", "地平线招聘", ("wecruit.hotjob.cn",), ("campus",)),
    JobProCompany("unitree", "宇树科技", "宇树科技招聘", ("www.unitree.com",), ("campus", "intern")),
    JobProCompany("megvii", "旷视", "旷视招聘", ("app.mokahr.com",), ("campus",)),
    JobProCompany("weride", "文远知行", "文远知行招聘", ("app.mokahr.com", "jobs.lever.co"), ("campus",)),
    JobProCompany("iqiyi", "爱奇艺", "爱奇艺招聘", ("careers.iqiyi.com",), ("campus", "intern")),
    JobProCompany("weibo", "微博", "微博招聘", ("app.mokahr.com",), ("all",), True),
    JobProCompany("deepseek", "DeepSeek", "DeepSeek招聘", ("app.mokahr.com",), ("all",), True),
    JobProCompany("moonshot", "Moonshot AI", "Moonshot招聘", ("app.mokahr.com",), ("all",), True),
    JobProCompany("stepfun", "阶跃星辰", "阶跃星辰招聘", ("app.mokahr.com",), ("all",), True),
    JobProCompany("zhipu", "智谱AI", "智谱AI招聘", ("zhipu-ai.jobs.feishu.cn",), ("all",), True),
    JobProCompany("galaxyuniversal", "银河通用", "银河通用招聘", ("app.mokahr.com",), ("all",), True),
)


EXCLUDED_COMPANIES = {
    "国资、院校或研究体系边界": ("中金", "海康威视", "科大讯飞", "寒武纪", "微众银行"),
    "暂不属于互联网或AI核心范围": ("比亚迪", "吉利", "理想", "蔚来", "小鹏", "顺丰", "平安"),
    "当前仅有第三方招聘平台数据": ("菜鸟",),
    "用户明确不纳入": ("零一万物", "百川智能"),
}
