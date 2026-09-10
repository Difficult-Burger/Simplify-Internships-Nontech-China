# 个性化岗位邮件订阅原型

此目录只用于产品开发与测试，不会合并到公开站点，也不会发送邮件、创建真实账户或产生扣款。

## 已实现的测试范围

- 邮箱登录入口和完整状态流转。
- 使用真实 `docs/jobs.json` 生成岗位类别、城市和公司选项。
- 岗位类别、招聘类型、城市、公司多选。
- 实时计算当前匹配岗位数并预览结果。
- 模拟购买与开启提醒的完成态。
- 可复用的岗位匹配、增量时间游标和邮件量估算函数。
- Supabase 数据表、最小权限 grants 和逐用户 RLS 策略。

## 生产架构候选

1. 公开岗位页继续由 GitHub Pages 免费提供，不要求登录。
2. Supabase Auth 使用邮箱 Magic Link；前端只持有 publishable key，绝不暴露 service role。
3. `alert_subscriptions` 只允许登录用户管理自己的筛选条件。
4. 支付 webhook 由服务端写入 `billing_entitlements`；客户端没有写权限，不能自行开通权益。
5. 每日岗位更新完成后，服务端只读取 `freshness_basis != baseline` 且晚于上次成功游标的岗位。
6. 每个用户每天最多收到一封汇总邮件；没有匹配岗位则不发送。
7. 邮件服务记录写入 `notification_deliveries`，用户只能查看自己的发送历史。

## 成本与定价边界（2026-09-01 快照）

- Supabase Free：$0，50,000 MAU、500 MB 数据库、500,000 Edge Function 调用；适合原型。生产 Pro 为 $25/月。
- Resend Free：$0，3,000 封/月且每天最多 100 封；每日一封模型在考虑登录邮件后，建议只测试约 80 名用户。Pro 为 $20/月、50,000 封。
- 两项都升级后固定成本至少 $45/月，尚未包含域名、支付手续费和税务成本。
- 若按 ¥4.99/月，使用 ¥7.1/USD 的测算假设，仅覆盖 $45 固定成本就需要约 65 名持续付费用户；低价下退款、客服和支付固定费用会进一步压缩空间。
- Stripe 官网明确其产品在中国大陆不可用；Stripe 的支付宝和微信支付也不能直接承担标准自动续费。因此不能把海外卡订阅当成中国用户的默认支付方案。

## 当前产品建议

- 免费岗位浏览永久保留。
- 第一轮只测试每日邮件汇总，不做“每出现一条立即发送”，否则邮件成本和打扰都会上升。
- 价格先在 ¥4.99、¥9.9、¥19.9 三档做意愿测试，不在原型中展示确定价格。
- 上线真实支付前必须先确定收款主体以及微信/支付宝商户能力；支付实现通过 provider adapter 接入，不改变订阅权益和邮件逻辑。

官方成本来源：

- https://supabase.com/pricing
- https://resend.com/pricing
- https://stripe.com/en-cn
- https://docs.stripe.com/payments/alipay
- https://docs.stripe.com/payments/wechat-pay

## 本地查看和测试

```bash
python -m http.server 8765
node --test tests/subscription-domain.test.mjs
```

打开 `http://localhost:8765/prototype/subscription/`。
