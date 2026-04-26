# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q04
- 维度: dyn_state_machine (3/5)
- 时间: 2026-04-23T20:35:32.939103

## 问题描述

SE-05（待交车状态下工单流转状态不变）标 COVERED，但未验证非法状态跳转拦截：工单在非待交车状态下发起提前交车申请时的状态机行为

## 证据

技术方案 4.3 泳道第2步：「执行 checkCanApplyEarlyDelivery 校验（判断工单状态是否符合申请条件）」，但未说明非法状态的具体拦截逻辑和返回码
