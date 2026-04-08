# /publicCharger/parking2/search和/publicCharger/parking2/detail接口查询时校验了xm_parking_info.timezone,但是存储的时候没有校验，导致这个字段如果有问题桩云会正常存储，但是查询接口直接报系统错误

- 所属需求: 停车场深度信息互联互通
- 二级分类: 函数异常分支未覆盖
- 提出日期: 2026-03-12

## 分析结果

若三方传的时区数据有问题，应该使用系统默认时区，以防止出现异常

## 单测改进措施

提高单测场景覆盖度
