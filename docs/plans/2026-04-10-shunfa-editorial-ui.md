# 顺发小程序编辑部视觉改造 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把顺发小程序的核心页面改造成统一的“编辑部晨报感”视觉，同时保持现有写作流程不变。

**Architecture:** 以 `app.wxss` 为统一 token 源，逐页替换为纸感背景、细边框卡片、荧光高亮和稿件式排版，再同步调整基础组件外观。只改视图层，不动接口契约和页面路由。

**Tech Stack:** 微信小程序 WXML、WXSS、现有 JS 页面逻辑

---

### Task 1: 全局视觉 token

**Files:**
- Modify: `miniprogram/app.wxss`

**Step 1: 写入新的颜色、圆角、阴影和共享按钮样式**

把纯工具风 token 改成纸感 + 编辑部风格，并补充共享标签、描边卡片和主次按钮样式。

**Step 2: 自查共享类名兼容性**

确认 `btn-primary`、`btn-ghost`、`card`、`section-title` 等已有类名不会影响现有页面逻辑。

### Task 2: 首页与选题页

**Files:**
- Modify: `miniprogram/pages/index/index.wxml`
- Modify: `miniprogram/pages/index/index.wxss`
- Modify: `miniprogram/pages/topics/topics.wxml`
- Modify: `miniprogram/pages/topics/topics.wxss`
- Modify: `miniprogram/components/topic-card/index.wxss`

**Step 1: 首页改成“今日发稿台”**

重组 hero、统计、等级、今日动作和提示模块，增加档期感和稿件隐喻。

**Step 2: 选题页改成“晨报选题单”**

强化来源、摘要、原文链接和“确认这个角度”的动作语义。

**Step 3: 统一热点卡片样式**

让选题卡片更像带编号的稿件卡，选中态更明确。

### Task 3: 预览页与我的页

**Files:**
- Modify: `miniprogram/pages/preview/preview.wxml`
- Modify: `miniprogram/pages/preview/preview.wxss`
- Modify: `miniprogram/pages/profile/profile.wxml`
- Modify: `miniprogram/pages/profile/profile.wxss`

**Step 1: 预览页改成“待发稿样张”**

把事实备注区、正文区、质量提示区和底部动作做成统一稿件视图。

**Step 2: 我的页改成“个人写作档案”**

弱化 dashboard 味道，强调累计写作记录、档案卡和提醒入口。

### Task 4: 基础组件收口

**Files:**
- Modify: `miniprogram/components/streak-badge/index.wxss`
- Modify: `miniprogram/components/diamond-display/index.wxss`
- Modify: `miniprogram/components/level-progress/index.wxss`

**Step 1: 统一连更、钻石、等级组件的边框和色彩系统**

与新首页和我的页保持同一套材质和层级。

### Task 5: 自查与验收

**Files:**
- Review: `miniprogram/pages/index/*`
- Review: `miniprogram/pages/topics/*`
- Review: `miniprogram/pages/preview/*`
- Review: `miniprogram/pages/profile/*`

**Step 1: 检查关键页面结构**

确认主要 CTA、原文链接、质量提示和提醒入口仍然可见且未被样式遮挡。

**Step 2: 汇总后续需要用户配置的内容**

把下一步微信小程序配置项整理给用户，包括 `baseUrl`、订阅消息模板等。
