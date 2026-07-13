# AgentOS Frontend

## 菜单结构

- 总览 → `/overview`
- 资源管理
  - 一体机 → `/resources/appliance`
  - 推理模型 → `/resources/inference-model`
    - 推理模型调用分析 → `/resources/inference-model/call-analysis`（隐藏侧栏）
    - 推理模型详情 → `/resources/inference-model/:id`（隐藏侧栏）
  - 智能体
    - 智能体监控 → `/resources/agent/monitor`
    - 框架管理 → `/resources/agent/framework`
  - 技能库 → `/resources/skill-store`
- 系统设置
  - 用户管理 → `/system/user-management`
  - 日志中心 → `/system/log-center`

## 目录结构

```
frontend/
├── public/                          # 公共静态资源
├── src/
│   ├── assets/
│   │   └── icons/                   # 菜单图标（占位）
│   ├── components/
│   │   └── layout/
│   │       ├── AppLayout.vue        # 整体布局（顶栏 + 侧栏 + 内容区）
│   │       ├── TopNav.vue           # 一级顶部菜单
│   │       └── SideMenu.vue         # 二三级左侧手风琴菜单
│   ├── router/
│   │   ├── index.ts                 # 创建 router 实例
│   │   └── menu.ts                  # 路由树（单一数据源）+ 菜单推导
│   ├── views/                       # 页面视图（按菜单模块划分）
│   │   ├── overview/
│   │   │   └── OverviewPage.vue     # 总览
│   │   ├── resources/
│   │   │   ├── AppliancePage.vue    # 一体机
│   │   │   ├── inference-model/                    # 推理模型
│   │   │   │   ├── InferenceModelListPage.vue      # 列表页
│   │   │   │   ├── InferenceModelCallAnalysisPage.vue # 调用分析页
│   │   │   │   ├── InferenceModelDetailPage.vue  # 详情页
│   │   │   │   ├── PerformanceMonitor.vue        # 性能监控
│   │   │   │   └── CallAnalysis.vue              # 调用分析内容
│   │   │   ├── SkillStorePage.vue   # 技能库
│   │   │   └── agent/               # 智能体
│   │   │       ├── AgentMonitorPage.vue  # 智能体监控
│   │   │       └── FrameworkPage.vue     # 框架管理
│   │   └── system/
│   │       ├── UserManagementPage.vue # 用户管理
│   │       └── LogCenterPage.vue      # 日志中心
│   ├── App.vue
│   ├── main.ts
│   ├── style.css                    # 全局样式与 CSS 变量
│   └── vite-env.d.ts
├── eslint.config.js
├── prettier.config.js
├── vite.config.ts
└── package.json
```

## 开发命令

```bash
# 启动开发服务器（需先启动后端，通过环境变量代理 /api 请求）
export VITE_PROXY_TARGET=http://{HOST}:{PORT} && npm run dev

npm run dev          # 启动开发服务器（不带代理）
npm run build        # 生产构建
npm run lint         # ESLint 检查
npm run format       # Prettier 格式化
npm run check        # 类型 + lint + 格式 一键检查
```

`VITE_PROXY_TARGET` 未设置时不启用代理，请求直接发往同源地址。
