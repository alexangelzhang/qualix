# AUDIT-037 — wmx-logistic-exchange

特批信息查询异常时主流程不崩溃

Rec: 建议加强断言：验证special_approval_id='' 当searchList抛异常时的降级行为
