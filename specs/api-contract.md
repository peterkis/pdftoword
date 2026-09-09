# 本地 Core API V1.1

- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `POST /v1/jobs/{job_id}/cancel`
- `POST /v1/jobs/{job_id}/retry`
- `GET /v1/jobs/{job_id}/ir`
- `GET /v1/jobs/{job_id}/pages/{page_index}/preview`
- `GET /v1/jobs/{job_id}/issues`
- `PATCH /v1/jobs/{job_id}/issues/{issue_id}`
- `POST /v1/jobs/{job_id}/regions/{region_id}/recognize`
- `POST /v1/jobs/{job_id}/export`
- `GET /v1/jobs/{job_id}/artifacts/{artifact_id}`
- `GET /v1/model-gateway/status`

所有写操作必须带本地会话 Token；资产请求验证作业归属；禁止任意路径参数。
