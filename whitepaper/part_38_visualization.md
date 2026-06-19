# 第三十八章：可视化与交互设计

## 38.1 监控面板架构

### 38.1.1 前端技术选型

**技术栈：**

```
前端框架：React 18 + TypeScript
状态管理：Zustand
UI组件库：Ant Design + ECharts
实时通信：WebSocket
构建工具：Vite
```

**选型理由：**

1. **React 18**：组件化开发，Concurrent特性提升渲染性能
2. **TypeScript**：类型安全，便于大型项目维护
3. **ECharts**：丰富的图表类型，适合数据可视化
4. **WebSocket**：实时推送Agent状态更新
5. **Vite**：快速开发体验，优化的生产构建

### 38.1.2 面板布局设计

```
┌─────────────────────────────────────────────────────────────┐
│  顶部导航栏                                                  │
│  [Logo] [系统状态: 运行中] [运行时间: 72h] [告警: 0]         │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                  │
│  左侧    │              主内容区                             │
│  导航    │                                                  │
│  菜单    │  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│          │  │  驱力雷达图  │  │  预测误差   │  │  资源使用 │ │
│  - 概览  │  │             │  │  趋势图     │  │          │ │
│  - 感知  │  └─────────────┘  └─────────────┘  └──────────┘ │
│  - 驱力  │                                                  │
│  - 任务  │  ┌──────────────────────────────────────────┐   │
│  - 预测  │  │           实时日志流                        │   │
│  - 进化  │  └──────────────────────────────────────────┘   │
│  - 安全  │                                                  │
│  - 设置  │  ┌─────────────┐  ┌─────────────┐              │
│          │  │  任务分布   │  │  模型性能   │              │
│          │  └─────────────┘  └─────────────┘              │
├──────────┴──────────────────────────────────────────────────┤
│  底部状态栏                                                  │
│  [CPU: 12%] [内存: 8%] [存储: 45%] [版本: v1.0.0]          │
└─────────────────────────────────────────────────────────────┘
```

### 38.1.3 实时数据流架构

```python
class DashboardWebSocket:
    """
    WebSocket实时数据推送服务
    """
    
    def __init__(self, agent):
        self.agent = agent
        self.clients = set()
        self.update_interval = 1.0  # 秒
        
    async def register_client(self, websocket):
        """注册新客户端"""
        self.clients.add(websocket)
        
        # 发送初始全量数据
        await self._send_full_state(websocket)
        
    async def broadcast_update(self):
        """广播状态更新"""
        if not self.clients:
            return
            
        update = await self._build_update()
        
        disconnected = set()
        for client in self.clients:
            try:
                await client.send_json(update)
            except:
                disconnected.add(client)
                
        # 清理断开连接
        self.clients -= disconnected
        
    async def _build_update(self) -> Dict:
        """构建增量更新数据"""
        stats = self.agent.get_stats()
        drives = self.agent.drive_engine.current_drive
        
        return {
            'timestamp': time.time(),
            'type': 'incremental',
            'data': {
                'cycle_count': stats['cycle_count'],
                'cycles_per_second': stats['cycles_per_second'],
                'average_error': stats['average_error'],
                'drives': {
                    'safe': drives.safe,
                    'gain': drives.gain,
                    'eff': drives.eff
                },
                'current_state': self.agent.state.value,
                'active_tasks': len(self.agent.task_generator.active_tasks)
            }
        }
```

## 38.2 核心可视化组件

### 38.2.1 驱力雷达图

```typescript
// React组件：驱力雷达图
import React from 'react';
import ReactECharts from 'echarts-for-react';

interface DriveData {
  safe: number;
  gain: number;
  eff: number;
}

const DriveRadarChart: React.FC<{ data: DriveData }> = ({ data }) => {
  const option = {
    radar: {
      indicator: [
        { name: '安全驱力', max: 1 },
        { name: '收益驱力', max: 1 },
        { name: '能效驱力', max: 1 }
      ],
      radius: '70%',
      splitNumber: 5,
      axisName: {
        color: '#333',
        fontSize: 14
      }
    },
    series: [{
      type: 'radar',
      data: [{
        value: [data.safe, data.gain, data.eff],
        name: '当前驱力',
        areaStyle: {
          color: 'rgba(24, 144, 255, 0.3)'
        },
        lineStyle: {
          color: '#1890ff',
          width: 2
        },
        itemStyle: {
          color: '#1890ff'
        }
      }]
    }]
  };

  return <ReactECharts option={option} style={{ height: 300 }} />;
};

export default DriveRadarChart;
```

### 38.2.2 预测误差实时趋势图

```typescript
// React组件：预测误差趋势
import React, { useState, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';

const ErrorTrendChart: React.FC = () => {
  const [data, setData] = useState<{ time: string; error: number }[]>([]);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8080/ws');
    
    ws.onmessage = (event) => {
      const update = JSON.parse(event.data);
      if (update.data.average_error !== undefined) {
        setData(prev => {
          const newData = [...prev, {
            time: new Date().toLocaleTimeString(),
            error: update.data.average_error
          }];
          // 保留最近100个点
          return newData.slice(-100);
        });
      }
    };

    return () => ws.close();
  }, []);

  const option = {
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: data.map(d => d.time),
      axisLabel: {
        rotate: 45,
        fontSize: 10
      }
    },
    yAxis: {
      type: 'value',
      name: '预测误差',
      min: 0
    },
    series: [{
      type: 'line',
      data: data.map(d => d.error),
      smooth: true,
      symbol: 'none',
      lineStyle: {
        color: '#52c41a',
        width: 2
      },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(82, 196, 26, 0.3)' },
            { offset: 1, color: 'rgba(82, 196, 26, 0.05)' }
          ]
        }
      }
    }],
    dataZoom: [{
      type: 'inside',
      start: 0,
      end: 100
    }]
  };

  return <ReactECharts option={option} style={{ height: 300 }} />;
};

export default ErrorTrendChart;
```

### 38.2.3 任务分布饼图

```typescript
// React组件：任务类型分布
import React from 'react';
import ReactECharts from 'echarts-for-react';

interface TaskDistribution {
  safe: number;
  gain: number;
  eff: number;
  exploring: number;
  exploiting: number;
}

const TaskDistributionChart: React.FC<{ data: TaskDistribution }> = ({ data }) => {
  const option = {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left'
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 10,
        borderColor: '#fff',
        borderWidth: 2
      },
      label: {
        show: false,
        position: 'center'
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 20,
          fontWeight: 'bold'
        }
      },
      data: [
        { value: data.safe, name: '安全任务', itemStyle: { color: '#ff4d4f' } },
        { value: data.gain, name: '收益任务', itemStyle: { color: '#52c41a' } },
        { value: data.eff, name: '能效任务', itemStyle: { color: '#1890ff' } },
        { value: data.exploring, name: '探索任务', itemStyle: { color: '#faad14' } },
        { value: data.exploiting, name: '利用任务', itemStyle: { color: '#722ed1' } }
      ]
    }]
  };

  return <ReactECharts option={option} style={{ height: 300 }} />;
};

export default TaskDistributionChart;
```

## 38.3 交互设计

### 38.3.1 人工干预接口

```typescript
// React组件：人工干预面板
import React, { useState } from 'react';
import { Card, Slider, Button, message, Modal } from 'antd';

const HumanInterventionPanel: React.FC = () => {
  const [weights, setWeights] = useState({ safe: 0.4, gain: 0.4, eff: 0.2 });
  const [isPaused, setIsPaused] = useState(false);

  const handleWeightChange = (type: string, value: number) => {
    setWeights(prev => ({ ...prev, [type]: value }));
  };

  const applyWeights = async () => {
    try {
      const response = await fetch('/api/intervention/weights', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(weights)
      });
      
      if (response.ok) {
        message.success('驱力权重已更新');
      }
    } catch (error) {
      message.error('更新失败');
    }
  };

  const togglePause = async () => {
    const endpoint = isPaused ? '/api/resume' : '/api/pause';
    
    try {
      const response = await fetch(endpoint, { method: 'POST' });
      if (response.ok) {
        setIsPaused(!isPaused);
        message.success(isPaused ? '系统已恢复' : '系统已暂停');
      }
    } catch (error) {
      message.error('操作失败');
    }
  };

  const triggerEmergencyStop = () => {
    Modal.confirm({
      title: '紧急停止',
      content: '确定要立即停止所有Agent活动吗？',
      okText: '确认停止',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await fetch('/api/emergency-stop', { method: 'POST' });
        message.success('系统已紧急停止');
      }
    });
  };

  return (
    <Card title="人工干预面板" extra={
      <Button type="primary" danger onClick={triggerEmergencyStop}>
        紧急停止
      </Button>
    }>
      <div style={{ marginBottom: 20 }}>
        <Button type={isPaused ? "primary" : "default"} onClick={togglePause}>
          {isPaused ? '恢复运行' : '暂停系统'}
        </Button>
      </div>

      <div style={{ marginBottom: 20 }}>
        <label>安全驱力权重: {weights.safe.toFixed(2)}</label>
        <Slider
          min={0}
          max={1}
          step={0.05}
          value={weights.safe}
          onChange={(v) => handleWeightChange('safe', v)}
        />
      </div>

      <div style={{ marginBottom: 20 }}>
        <label>收益驱力权重: {weights.gain.toFixed(2)}</label>
        <Slider
          min={0}
          max={1}
          step={0.05}
          value={weights.gain}
          onChange={(v) => handleWeightChange('gain', v)}
        />
      </div>

      <div style={{ marginBottom: 20 }}>
        <label>能效驱力权重: {weights.eff.toFixed(2)}</label>
        <Slider
          min={0}
          max={1}
          step={0.05}
          value={weights.eff}
          onChange={(v) => handleWeightChange('eff', v)}
        />
      </div>

      <Button type="primary" onClick={applyWeights}>
        应用权重调整
      </Button>
    </Card>
  );
};

export default HumanInterventionPanel;
```

### 38.3.2 实时日志流

```typescript
// React组件：实时日志
import React, { useState, useEffect, useRef } from 'react';
import { List, Tag } from 'antd';

interface LogEntry {
  id: string;
  timestamp: string;
  level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG';
  message: string;
  source: string;
}

const LogStream: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8080/ws/logs');
    
    ws.onmessage = (event) => {
      const log: LogEntry = JSON.parse(event.data);
      setLogs(prev => {
        const newLogs = [log, ...prev];
        return newLogs.slice(0, 1000); // 保留最近1000条
      });
    };

    return () => ws.close();
  }, []);

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'ERROR': return 'red';
      case 'WARNING': return 'orange';
      case 'INFO': return 'blue';
      case 'DEBUG': return 'gray';
      default: return 'default';
    }
  };

  return (
    <div ref={listRef} style={{ height: 400, overflow: 'auto' }}>
      <List
        dataSource={logs}
        renderItem={log => (
          <List.Item>
            <div style={{ fontFamily: 'monospace', fontSize: 12 }}>
              <span style={{ color: '#999' }}>{log.timestamp}</span>
              {' '}
              <Tag color={getLevelColor(log.level)}>{log.level}</Tag>
              {' '}
              <span style={{ color: '#666' }}>[{log.source}]</span>
              {' '}
              <span>{log.message}</span>
            </div>
          </List.Item>
        )}
      />
    </div>
  );
};

export default LogStream;
```

## 38.4 移动端适配

### 38.4.1 响应式布局

```typescript
// 响应式布局组件
import React from 'react';
import { Row, Col } from 'antd';

const ResponsiveDashboard: React.FC = () => {
  return (
    <Row gutter={[16, 16]}>
      {/* 驱力雷达图 - 移动端全宽，桌面端1/3 */}
      <Col xs={24} sm={24} md={12} lg={8}>
        <DriveRadarCard />
      </Col>
      
      {/* 误差趋势 - 移动端全宽，桌面端1/3 */}
      <Col xs={24} sm={24} md={12} lg={8}>
        <ErrorTrendCard />
      </Col>
      
      {/* 资源使用 - 移动端全宽，桌面端1/3 */}
      <Col xs={24} sm={24} md={12} lg={8}>
        <ResourceUsageCard />
      </Col>
      
      {/* 日志流 - 始终全宽 */}
      <Col xs={24}>
        <LogStreamCard />
      </Col>
      
      {/* 任务分布 - 移动端全宽，桌面端1/2 */}
      <Col xs={24} sm={24} md={12}>
        <TaskDistributionCard />
      </Col>
      
      {/* 模型性能 - 移动端全宽，桌面端1/2 */}
      <Col xs={24} sm={24} md={12}>
        <ModelPerformanceCard />
      </Col>
    </Row>
  );
};

export default ResponsiveDashboard;
```

## 38.5 本章小结

本章提供了自驱永续进化Agent系统的可视化与交互设计方案：

1. **监控面板架构**：前端技术选型、布局设计、实时数据流
2. **核心可视化组件**：驱力雷达图、误差趋势图、任务分布图
3. **交互设计**：人工干预面板、实时日志流
4. **移动端适配**：响应式布局

这些设计确保了系统的可观测性和人机协同能力。
