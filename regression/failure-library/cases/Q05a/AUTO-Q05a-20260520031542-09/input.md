# 自动生成的 Bug Case

- 项目: home-replace-renewal
- Phase: Q05a
- 时间: 2026-05-20T03:15:42.867838

## Validation Error

Value error, assertThrows 必须指定具体业务异常类，不能用 Exception/RuntimeException/Throwable: 'assertThrows(RuntimeException.class, () -> service.logisticExchangeMark("", "HH"))'。请改为具体类（如 MafSrvAftersaleException.class、BusinessException.class）。 [type=value_error, input_value='assertThrows(RuntimeExce...ExchangeMark("", "HH"))', input_type=str]
