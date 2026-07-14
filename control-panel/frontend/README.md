# AgentOS Frontend

## 菜单结构

- 总览 → `/overview`
- 资源管理
  - 一体机 → `/resources/appliance`
  - 推理模型 → `/resources/inference-model`
    - 模型监控 → `/resources/inference-model`（默认子页）
    - API Key → `/resources/inference-model/api-key`
    - 调用分析 → `/resources/inference-model/call-analysis`（隐藏侧栏）
    - 模型详情 → `/resources/inference-model/:id`（隐藏侧栏）
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
│   ├── api/
│   │   ├── index.ts                 # Axios 实例 + 请求/响应拦截器 + 泛型方法
│   │   ├── inference.ts             # 推理模型 & API Key API（含 DEV mock）
│   │   └── types.ts                 # 共享类型定义
│   ├── assets/
│   │   ├── icons/                   # 菜单图标
│   │   └── models/                  # 模型图标（DeepSeek、glm、MiniMax）
│   ├── components/
│   │   └── layout/
│   │       ├── AppLayout.vue        # 整体布局（顶栏 + 侧栏 + 内容区）
│   │       ├── TopNav.vue           # 一级顶部菜单
│   │       └── SideMenu.vue         # 二三级左侧手风琴菜单
│   ├── router/
│   │   ├── index.ts                 # 创建 router 实例
│   │   └── menu.ts                  # 路由树（单一数据源）+ 菜单推导
│   ├── views/
│   │   ├── overview/
│   │   │   └── OverviewPage.vue     # 总览
│   │   ├── resources/
│   │   │   ├── AppliancePage.vue    # 一体机
│   │   │   ├── SkillStorePage.vue   # 技能库
│   │   │   ├── inference/           # 推理模型模块
│   │   │   │   ├── InferenceModelDashboard.vue   # 模型监控主页（概览卡片 + 模型网格）
│   │   │   │   ├── InferenceModelDetail.vue      # 模型详情页（元数据 + 性能监控）
│   │   │   │   ├── InferenceApiKeyPage.vue       # API Key 管理（CRUD + 分页）
│   │   │   │   ├── AddModelModal.vue             # 添加模型抽屉（表单）
│   │   │   │   ├── ModelCard.vue                 # 模型卡片（状态 + 指标 + 操作）
│   │   │   │   ├── ModelInfoDrawer.vue           # 模型信息抽屉（查看/编辑模式）
│   │   │   │   ├── ModelInfoRow.vue              # 信息行（label-value）
│   │   │   │   ├── ChartCard.vue                 # 图表卡片容器
│   │   │   │   ├── DataTable.vue                 # 通用数据表格
│   │   │   │   └── MetricDisplay.vue             # 指标展示（值 + 趋势）
│   │   │   ├── inference-model/     # 上游推理模型组件
│   │   │   │   ├── InferenceModelListPage.vue
│   │   │   │   ├── InferenceModelCallAnalysisPage.vue
│   │   │   │   ├── InferenceModelDetailPage.vue
│   │   │   │   ├── PerformanceMonitor.vue
│   │   │   │   └── CallAnalysis.vue
│   │   │   └── agent/
│   │   │       ├── AgentMonitorPage.vue
│   │   │       └── FrameworkPage.vue
│   │   └── system/
│   │       ├── UserManagementPage.vue
│   │       └── LogCenterPage.vue
│   ├── App.vue
│   ├── main.ts
│   ├── style.css                    # 全局样式与 CSS 变量
│   └── vite-env.d.ts
├── eslint.config.js
├── prettier.config.js
├── vite.config.ts
└── package.json
```

## API 层

所有 HTTP 请求通过 `api/index.ts` 的 axios 实例统一管理，响应自动解包 `ApiResponse<T>`。

### 推理模型 API (`api/inference.ts`)

| 函数 | 方法 | 路径 | 说明 |
|------|------|------|------|
| `fetchModelList(params?)` | GET | `/api/inference-models` | 模型列表，支持 status/keyword 筛选 |
| `fetchModelDetail(id)` | GET | `/api/inference-models/${id}` | 模型详情 |
| `createModel(data)` | POST | `/api/inference-models` | 创建模型 |
| `updateModel(id, data)` | PUT | `/api/inference-models/${id}` | 更新模型 |
| `deleteModel(id)` | DELETE | `/api/inference-models/${id}` | 删除模型 |
| `restartModel(id)` | POST | `/api/inference-models/${id}/restart` | 重启模型 |

### API Key API (`api/inference.ts`)

| 函数 | 方法 | 路径 | 说明 |
|------|------|------|------|
| `fetchApiKeyList()` | GET | `/api/api-keys` | API Key 列表 |
| `createApiKey(data)` | POST | `/api/api-keys` | 创建 API Key |
| `deleteApiKey(id)` | DELETE | `/api/api-keys/${id}` | 删除 API Key |

> **Mock 模式**：开发环境（`import.meta.env.DEV`）自动使用 mock 数据，生产环境走真实 HTTP 请求。

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

## 路由配置说明

所有路由在 `menu.ts` 的 `appRouteTree` 中统一配置，`index.ts` 只负责创建 router 实例。

**新增页面步骤：**
1. 在 `menu.ts` 的 `appRouteTree` 对应模块的 `children` 中添加路由节点
2. 创建对应的 Vue 组件文件
3. 运行 `npm run check` 验证

**路由节点属性：**
- `key`: 唯一标识
- `label`: 菜单显示文本
- `order`: 排序序号
- `path`: 路由路径
- `name`: 路由名称（用于编程式导航）
- `component`: 组件懒加载
- `hideInMenu`: 隐藏菜单项
- `hideSideMenu`: 隐藏侧边栏
- `defaultChildKey`: 默认选中的子项

## 依赖

- Vue 3 + TypeScript
- Vue Router
- Element Plus（UI 组件库，按需导入）
- Axios（HTTP 请求）

`VITE_PROXY_TARGET` 未设置时不启用代理，请求直接发往同源地址。
