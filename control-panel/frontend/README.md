# AgentOS Frontend

## 菜单结构

- 总览 → `/overview`
- 资源管理
  - 一体机 → `/resources/appliance`
  - 推理模型 → `/resources/inference-model`
  - 智能体
    - 智能体监控 → `/resources/agent/monitor`
    - 框架管理 → `/resources/agent/framework`
  - 技能库 → `/resources/skill-store`
- 系统设置 → `/settings`

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
│   │   │   ├── InferenceModelPage.vue # 推理模型
│   │   │   ├── SkillStorePage.vue   # 技能库
│   │   │   └── agent/               # 智能体
│   │   │       ├── AgentMonitorPage.vue  # 智能体监控
│   │   │       └── FrameworkPage.vue     # 框架管理
│   │   └── settings/
│   │       └── SettingsPage.vue     # 系统设置
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
npm run dev          # 启动开发服务器
npm run build        # 生产构建
npm run lint         # ESLint 检查
npm run format       # Prettier 格式化
npm run check        # 类型 + lint + 格式 一键检查
```
