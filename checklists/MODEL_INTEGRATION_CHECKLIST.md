# 模型集成检查表

- [ ] 只通过 8100 网关。
- [ ] 模型 ID/revision/hash 可追溯。
- [ ] 请求有 timeout/retry/idempotency。
- [ ] 坐标单位明确并有测试。
- [ ] 原始响应保存为受控资产。
- [ ] 未伪造模型置信度。
- [ ] 未直接覆盖候选。
- [ ] 失败有降级。
- [ ] 日志无图像和正文。
- [ ] trust_remote_code 已固定 revision 和隔离。
