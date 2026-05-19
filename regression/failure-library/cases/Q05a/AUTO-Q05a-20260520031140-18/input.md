# 自动生成的 Bug Case

- 项目: home-replace-renewal
- Phase: Q05a
- 时间: 2026-05-20T03:11:40.892768

## Validation Error

Value error, assertThrows 必须指定具体业务异常类，不能用 Exception/RuntimeException/Throwable: 'assertThrows(RuntimeException.class, () -> service.logisticExchangeMark("SVC008", "HH"))'。请改为具体类（如 MafSrvAftersaleException.class、BusinessException.class）。 [type=value_error, input_value='assertThrows(RuntimeExce...geMark("SVC008", "HH"))', input_type=str]
