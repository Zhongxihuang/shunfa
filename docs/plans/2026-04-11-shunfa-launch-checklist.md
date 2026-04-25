# 顺发小程序上线检查清单

**日期**: 2026-04-11

## 后端

- Railway 生产环境已配置：
  - `WECHAT_APP_ID`
  - `WECHAT_APP_SECRET`
  - `JWT_SECRET_KEY`
  - `DEEPSEEK_API_KEY`
  - `WECHAT_SUBSCRIBE_TEMPLATE_ID`
  - `WECHAT_SUBSCRIBE_PAGE=pages/index/index`
  - `WECHAT_SUBSCRIBE_THING_KEY=thing3`
  - `WECHAT_SUBSCRIBE_TIME_KEY=time1`
  - `WECHAT_SUBSCRIBE_PHRASE_KEY=thing2`
  - `WECHAT_SUBSCRIBE_PROJECT_KEY=thing15`
- 数据库已执行最新迁移：
  - `alembic upgrade head`
- 生产健康检查可访问：
  - `https://shunfa-production.up.railway.app/health`

## 小程序后台

- 小程序 AppID 确认：
  - `wxe4153d38a954fb22`
- 微信公众平台已配置 `request 合法域名`：
  - `https://shunfa-production.up.railway.app`
- 订阅消息模板已创建
- 模板字段已确认：
  - `time1`
  - `thing3`
  - `thing2`
  - `thing15`

## 小程序前端

- [config.js](/Users/huangzhongxi/shunfa/miniprogram/config.js) 已填入订阅消息模板 ID
- 开发环境指向：
  - `http://127.0.0.1:8000`
- 生产环境指向：
  - `https://shunfa-production.up.railway.app`

## 已验证功能

- `wx.login -> /api/login` 已打通
- 热点结构化接口可用
- 选题 -> 起稿 -> 预览主流程可用
- 提醒设置保存可用
- 本地手动触发订阅消息发送可用：
  - `{"checked":1,"sent":1,"skipped":0,"failed":0}`

## 尚未完成的验证

- 微信开发者工具 `真机调试 / 预览空白` 问题未排查完成
- 真机实际收到并点击订阅消息后的跳转页，尚未完成闭环验证
- Railway 线上环境建议再执行一次真实 `send_due` 验证

## 上线前最后一次建议验收

1. 在生产环境小程序里保存提醒设置
2. 让提醒时间落在当前时间前 1-5 分钟内
3. 在线上触发一次 `/api/reminder/send_due`
4. 确认微信实际收到订阅消息
5. 点击消息，确认跳转到 `pages/index/index`
