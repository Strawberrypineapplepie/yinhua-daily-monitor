# 银华日利监控器配置

## 环境变量配置

### 必需配置 (已配置)
```bash
# 妙想API Key
setx MX_APIKEY "mkt_ahXg1oOYPC-dBuTsOWZJdTQApZ6SA2vZkNNHxdnpHlI"

# 飞书开放平台配置 (已内置默认值)
setx FEISHU_APP_ID "cli_a92fee8f66791cd1"
setx FEISHU_APP_SECRET "your-app-secret"  # 已内置
setx FEISHU_RECEIVE_ID "ou_9457a90140c97c4d7ff683801686ba56"  # 接收消息的用户
setx FEISHU_RECEIVE_TYPE "open_id"  # 接收者类型
```

## 数据源

1. **主要**: 东方财富妙想API (需MX_APIKEY)
2. **备用**: 东方财富公开接口
3. **第三备用**: 腾讯股票接口

## 定时任务配置 (已配置)

### Windows 任务计划 (已创建任务: YinhuaDailyMonitor)
- **执行时间**: 每天开市时间 09:30 - 15:00
- **执行间隔**: 每 10 分钟
- **任务名称**: YinhuaDailyMonitor
- **启动脚本**: `scripts/run_monitor.bat`

### 手动执行
```bash
# 单次检测 (推荐测试用)
python yinhua_monitor.py --once

# 持续监控模式
python yinhua_monitor.py --daemon

# 不发送飞书通知
python yinhua_monitor.py --once --no-push
```

### 管理定时任务
```bash
# 查看任务状态
schtasks /query /tn "YinhuaDailyMonitor"

# 立即运行一次
schtasks /run /tn "YinhuaDailyMonitor"

# 暂停任务
schtasks /change /tn "YinhuaDailyMonitor" /disable

# 恢复任务
schtasks /change /tn "YinhuaDailyMonitor" /enable

# 删除任务
schtasks /delete /tn "YinhuaDailyMonitor" /f
```

## 策略参数 (来自策略文档)

| 参数 | 值 | 说明 |
|------|-----|------|
| 折价阈值 | 万0.8 | 折价赎回套利触发 |
| 溢价阈值 | 万1.5 | 溢价申购套利触发 |
| 做T阈值 | 万0.5 | 日内做T触发 |
| 周二阈值 | 万1 | 周二特殊策略 |
| 日收益速算值 | 万0.35 | 预估净值计算 |

## 飞书消息示例

监控器会发送交互式卡片消息，包含：
- 当前价格和IOPV
- 折溢价状态
- 策略建议
- 预期收益

## 故障排查

### 1. 数据获取失败
- 检查网络连接
- 验证 MX_APIKEY 是否有效
- 检查东方财富/腾讯接口可访问性

### 2. 飞书推送失败
- 检查飞书应用是否有消息发送权限
- 验证接收者 open_id 是否正确
- 查看 im:message:send 权限是否已授权

### 3. 定时任务不执行
- 检查任务是否启用: `schtasks /query /tn "YinhuaDailyMonitor"`
- 查看任务历史日志
- 确认脚本路径正确
