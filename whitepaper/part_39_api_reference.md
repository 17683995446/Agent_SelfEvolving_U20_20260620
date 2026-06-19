# 第三十九章：API参考文档

## 39.1 REST API概述

### 39.1.1 API设计原则

**RESTful设计：**
- 使用HTTP方法表示操作（GET/POST/PUT/DELETE）
- 使用URL路径表示资源
- 使用HTTP状态码表示结果
- 使用JSON格式传输数据

**版本控制：**
- URL路径包含版本号：`/api/v1/...`
- 支持多版本并行

**认证授权：**
- 基于Token的认证
- 支持API Key
- 请求频率限制

### 39.1.2 基础信息

**Base URL：** `http://localhost:8080/api/v1`

**请求格式：**
```
Content-Type: application/json
Authorization: Bearer <token>
```

**响应格式：**
```json
{
  "code": 200,
  "message": "success",
  "data": {},
  "timestamp": 1704067200
}
```

**错误响应：**
```json
{
  "code": 400,
  "message": "Bad Request",
  "error": "Invalid parameter",
  "timestamp": 1704067200
}
```

## 39.2 系统管理API

### 39.2.1 获取系统状态

**请求：**
```
GET /system/status
```

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "state": "running",
    "version": "1.0.0",
    "uptime_seconds": 259200,
    "cycle_count": 100000,
    "cycles_per_second": 0.5,
    "current_drive": {
      "safe": 0.3,
      "gain": 0.5,
      "eff": 0.2
    },
    "current_weights": {
      "w_safe": 0.4,
      "w_gain": 0.4,
      "w_eff": 0.2
    },
    "active_tasks": 5,
    "pending_tasks": 12,
    "prediction_error": 0.05
  }
}
```

### 39.2.2 获取系统统计

**请求：**
```
GET /system/stats
```

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| period | string | 否 | 统计周期：hour/day/week/month |

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "period": "day",
    "cycles_completed": 43200,
    "tasks_executed": 150,
    "average_error": 0.048,
    "error_trend": -0.002,
    "resource_usage": {
      "cpu_avg": 12.5,
      "cpu_max": 18.2,
      "memory_avg": 256,
      "memory_max": 512
    },
    "drive_history": [
      {
        "timestamp": 1704067200,
        "safe": 0.3,
        "gain": 0.5,
        "eff": 0.2
      }
    ]
  }
}
```

### 39.2.3 暂停系统

**请求：**
```
POST /system/pause
```

**响应：**
```json
{
  "code": 200,
  "message": "System paused",
  "data": {
    "previous_state": "running",
    "current_state": "paused"
  }
}
```

### 39.2.4 恢复系统

**请求：**
```
POST /system/resume
```

**响应：**
```json
{
  "code": 200,
  "message": "System resumed",
  "data": {
    "previous_state": "paused",
    "current_state": "running"
  }
}
```

### 39.2.5 紧急停止

**请求：**
```
POST /system/emergency-stop
```

**说明：** 立即停止所有Agent活动，进入安全状态

**响应：**
```json
{
  "code": 200,
  "message": "Emergency stop activated",
  "data": {
    "timestamp": 1704067200,
    "actions_taken": [
      "All tasks cancelled",
      "Models saved",
      "Resources released"
    ]
  }
}
```

## 39.3 感知API

### 39.3.1 获取当前感知状态

**请求：**
```
GET /perception/current
```

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "timestamp": 1704067200,
    "system": {
      "cpu_percent": 15.2,
      "memory_percent": 45.6,
      "disk_percent": 62.3,
      "network_io_mbps": 1.2,
      "load_average": [0.5, 0.6, 0.7]
    },
    "logs": {
      "new_entries": 10,
      "error_count": 0,
      "warning_count": 2,
      "error_rate": 0.0
    },
    "files": {
      "new_files": 3,
      "modified_files": 5,
      "deleted_files": 1,
      "total_files": 1250
    },
    "self": {
      "cpu_percent": 2.1,
      "memory_mb": 128,
      "threads": 8
    }
  }
}
```

### 39.3.2 获取感知历史

**请求：**
```
GET /perception/history
```

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start_time | integer | 是 | 开始时间戳 |
| end_time | integer | 是 | 结束时间戳 |
| sensor_type | string | 否 | 传感器类型过滤 |
| limit | integer | 否 | 返回数量限制，默认100 |

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1000,
    "records": [
      {
        "timestamp": 1704067200,
        "sensor_type": "system",
        "values": {
          "cpu_percent": 15.2,
          "memory_percent": 45.6
        }
      }
    ]
  }
}
```

## 39.4 驱力API

### 39.4.1 获取当前驱力状态

**请求：**
```
GET /drive/current
```

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "drives": {
      "safe": 0.3,
      "gain": 0.5,
      "eff": 0.2
    },
    "weights": {
      "w_safe": 0.4,
      "w_gain": 0.4,
      "w_eff": 0.2
    },
    "gaps": {
      "safe_gap": 0.28,
      "gain_gap": 0.20,
      "eff_gap": 0.16,
      "total_gap": 0.64
    },
    "emergency": false,
    "dominant_drive": "gain"
  }
}
```

### 39.4.2 获取驱力历史

**请求：**
```
GET /drive/history
```

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | integer | 否 | 返回数量，默认100 |

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "records": [
      {
        "timestamp": 1704067200,
        "safe": 0.3,
        "gain": 0.5,
        "eff": 0.2,
        "safe_gap": 0.28,
        "gain_gap": 0.20,
        "eff_gap": 0.16
      }
    ]
  }
}
```

### 39.4.3 更新驱力权重

**请求：**
```
POST /drive/weights
```

**请求体：**
```json
{
  "w_safe": 0.5,
  "w_gain": 0.3,
  "w_eff": 0.2
}
```

**说明：** 权重必须满足 w_safe + w_gain + w_eff = 1.0

**响应：**
```json
{
  "code": 200,
  "message": "Weights updated",
  "data": {
    "previous_weights": {
      "w_safe": 0.4,
      "w_gain": 0.4,
      "w_eff": 0.2
    },
    "current_weights": {
      "w_safe": 0.5,
      "w_gain": 0.3,
      "w_eff": 0.2
    }
  }
}
```

## 39.5 任务API

### 39.5.1 获取任务列表

**请求：**
```
GET /tasks
```

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 状态过滤：pending/running/completed/failed |
| type | string | 否 | 类型过滤：safe/gain/eff |
| limit | integer | 否 | 返回数量，默认50 |
| offset | integer | 否 | 偏移量，默认0 |

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 150,
    "tasks": [
      {
        "id": "task_001",
        "name": "CPU异常检测",
        "type": "safe",
        "status": "running",
        "priority": "high",
        "expected_reward": 0.8,
        "actual_reward": null,
        "created_at": 1704067200,
        "started_at": 1704067205,
        "completed_at": null
      }
    ]
  }
}
```

### 39.5.2 获取任务详情

**请求：**
```
GET /tasks/{task_id}
```

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "task_001",
    "name": "CPU异常检测",
    "description": "监控系统CPU使用率，检测异常模式",
    "type": "safe",
    "status": "running",
    "priority": "high",
    "expected_reward": 0.8,
    "expected_cost": 0.1,
    "actual_reward": null,
    "actual_cost": null,
    "execution_count": 1,
    "success_count": 0,
    "failure_count": 0,
    "created_at": 1704067200,
    "started_at": 1704067205,
    "completed_at": null,
    "metadata": {
      "target_metric": "cpu_percent",
      "threshold": 80.0
    }
  }
}
```

### 39.5.3 创建人工任务

**请求：**
```
POST /tasks
```

**请求体：**
```json
{
  "name": "手动磁盘清理",
  "description": "清理过期日志文件",
  "type": "eff",
  "priority": "medium",
  "expected_reward": 0.6,
  "expected_cost": 0.2,
  "metadata": {
    "target_directory": "/var/log",
    "retention_days": 30
  }
}
```

**响应：**
```json
{
  "code": 201,
  "message": "Task created",
  "data": {
    "id": "task_manual_001",
    "name": "手动磁盘清理",
    "status": "pending",
    "created_at": 1704067200
  }
}
```

### 39.5.4 取消任务

**请求：**
```
DELETE /tasks/{task_id}
```

**响应：**
```json
{
  "code": 200,
  "message": "Task cancelled",
  "data": {
    "id": "task_001",
    "previous_status": "running",
    "current_status": "cancelled"
  }
}
```

## 39.6 预测API

### 39.6.1 获取预测结果

**请求：**
```
GET /prediction/current
```

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| horizon | integer | 否 | 预测步数，默认10 |
| level | string | 否 | 预测层级：low/mid/high/ensemble |

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "timestamp": 1704067200,
    "level": "ensemble",
    "horizon": 10,
    "predictions": [
      {
        "step": 1,
        "value": 15.2,
        "confidence": 0.92,
        "lower_bound": 14.5,
        "upper_bound": 15.9
      }
    ],
    "model_version": "v1.2.3"
  }
}
```

### 39.6.2 获取预测历史

**请求：**
```
GET /prediction/history
```

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start_time | integer | 是 | 开始时间戳 |
| end_time | integer | 是 | 结束时间戳 |
| limit | integer | 否 | 返回数量，默认100 |

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "records": [
      {
        "timestamp": 1704067200,
        "predicted_value": 15.2,
        "actual_value": 15.5,
        "error": 0.3,
        "confidence": 0.92,
        "model_version": "v1.2.3"
      }
    ]
  }
}
```

### 39.6.3 触发模型重构

**请求：**
```
POST /prediction/rebuild
```

**请求体：**
```json
{
  "level": "mid",
  "reason": "预测误差持续升高"
}
```

**响应：**
```json
{
  "code": 202,
  "message": "Rebuild triggered",
  "data": {
    "rebuild_id": "rebuild_001",
    "level": "mid",
    "status": "in_progress",
    "estimated_duration": 300
  }
}
```

## 39.7 记忆API

### 39.7.1 获取记忆统计

**请求：**
```
GET /memory/stats
```

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "short_term": {
      "entries": 100,
      "size_mb": 10.5
    },
    "long_term": {
      "entries": 10000,
      "size_mb": 256.0
    },
    "snapshots": {
      "count": 10,
      "total_size_mb": 512.0
    }
  }
}
```

### 39.7.2 创建快照

**请求：**
```
POST /memory/snapshots
```

**请求体：**
```json
{
  "name": "pre_upgrade_backup",
  "description": "升级前的完整备份"
}
```

**响应：**
```json
{
  "code": 201,
  "message": "Snapshot created",
  "data": {
    "id": "snapshot_001",
    "name": "pre_upgrade_backup",
    "created_at": 1704067200,
    "size_mb": 128.5
  }
}
```

### 39.7.3 恢复快照

**请求：**
```
POST /memory/snapshots/{snapshot_id}/restore
```

**响应：**
```json
{
  "code": 200,
  "message": "Snapshot restored",
  "data": {
    "snapshot_id": "snapshot_001",
    "restored_at": 1704067200,
    "previous_state": "running",
    "current_state": "running"
  }
}
```

## 39.8 安全API

### 39.8.1 获取安全状态

**请求：**
```
GET /safety/status
```

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "state": "normal",
    "active_constraints": [
      "cpu_limit",
      "memory_limit",
      "forbidden_paths"
    ],
    "recent_violations": [],
    "violation_count_24h": 0
  }
}
```

### 39.8.2 获取违规历史

**请求：**
```
GET /safety/violations
```

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | integer | 否 | 返回数量，默认50 |
| severity | string | 否 | 严重程度过滤 |

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "violations": [
      {
        "id": "vio_001",
        "timestamp": 1704067200,
        "type": "resource_limit",
        "severity": "medium",
        "description": "CPU使用率超过阈值",
        "action_taken": "降低采样频率"
      }
    ]
  }
}
```

## 39.9 配置API

### 39.9.1 获取当前配置

**请求：**
```
GET /config
```

**响应：**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "agent_name": "SelfEvolvingAgent",
    "version": "1.0.0",
    "loop_interval": 1.0,
    "resource_limits": {
      "max_cpu_percent": 20.0,
      "max_memory_percent": 20.0
    },
    "drive_weights": {
      "safe": 0.4,
      "gain": 0.4,
      "eff": 0.2
    }
  }
}
```

### 39.9.2 更新配置

**请求：**
```
PUT /config
```

**请求体：**
```json
{
  "loop_interval": 2.0,
  "drive_weights": {
    "safe": 0.5,
    "gain": 0.3,
    "eff": 0.2
  }
}
```

**说明：** 只更新提供的字段，未提供的字段保持不变

**响应：**
```json
{
  "code": 200,
  "message": "Config updated",
  "data": {
    "updated_fields": ["loop_interval", "drive_weights"],
    "requires_restart": false
  }
}
```

## 39.10 WebSocket API

### 39.10.1 实时状态流

**连接：**
```
ws://localhost:8080/ws
```

**认证：**
```
ws://localhost:8080/ws?token=<access_token>
```

**消息格式：**
```json
{
  "type": "status_update",
  "timestamp": 1704067200,
  "data": {
    "cycle_count": 100001,
    "drives": {
      "safe": 0.3,
      "gain": 0.5,
      "eff": 0.2
    },
    "prediction_error": 0.048
  }
}
```

### 39.10.2 日志流

**连接：**
```
ws://localhost:8080/ws/logs
```

**过滤参数：**
```
ws://localhost:8080/ws/logs?level=ERROR&source=predictor
```

**消息格式：**
```json
{
  "type": "log",
  "timestamp": 1704067200,
  "data": {
    "level": "ERROR",
    "source": "predictor",
    "message": "Prediction failed: model timeout"
  }
}
```

## 39.11 错误码参考

| 错误码 | 含义 | 说明 |
|--------|------|------|
| 200 | 成功 | 请求处理成功 |
| 201 | 已创建 | 资源创建成功 |
| 202 | 已接受 | 请求已接受，正在处理 |
| 400 | 请求参数错误 | 请求参数不合法 |
| 401 | 未授权 | 认证失败或Token过期 |
| 403 | 禁止访问 | 权限不足 |
| 404 | 资源不存在 | 请求的资源不存在 |
| 409 | 资源冲突 | 资源状态冲突 |
| 422 | 无法处理 | 请求语义错误 |
| 429 | 请求过于频繁 | 超过频率限制 |
| 500 | 服务器内部错误 | 服务器异常 |
| 503 | 服务不可用 | 系统维护或过载 |

## 39.12 本章小结

本章提供了自驱永续进化Agent系统的完整API参考文档：

1. **系统管理API**：状态查询、暂停/恢复、紧急停止
2. **感知API**：当前状态、历史数据
3. **驱力API**：驱力状态、权重调整
4. **任务API**：任务列表、详情、创建、取消
5. **预测API**：预测结果、历史、模型重构
6. **记忆API**：统计、快照创建/恢复
7. **安全API**：安全状态、违规历史
8. **配置API**：配置查询、更新
9. **WebSocket API**：实时状态流、日志流
10. **错误码参考**：完整的错误码列表

这些API为系统集成和二次开发提供了完整的接口支持。
