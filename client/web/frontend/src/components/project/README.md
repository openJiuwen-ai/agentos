# 创建项目 UI 模块

## 页面接入

已挂到 `Sidebar.tsx`：

- `ProjectSectionHeader`：项目标题旁悬浮 `+`
- `CreateProjectDialog`：新建弹窗
- `useCreateProjectFlow`：联动 jiuwenswarm 后端

## 后端调用链（jiuwenswarm WS RPC）

```text
弹窗确定
  → useCreateProjectFlow.submit
  → workspaceStore.createProject
  → projectRegistryClient.create  →  method: project.create
  → workspaceStore.loadProjects   →  method: project.list
  → loadProjectSessions           →  method: project.get_sessions
```

## 选择已有目录

| 环境 | 行为 |
|------|------|
| **桌面客户端**（pywebview，`window.pywebview.api.select_project_directory`） | 点路径框（空时）或「浏览」→ 系统文件夹对话框 → 回填绝对路径；名称为空时用文件夹名 |
| **网页浏览器** | 无法拿到真实绝对路径；提示手动粘贴；点「浏览」会提示不支持 |

创建仍走 `project.create`；路径留空则后端自动建目录。

## 相关文件

| 路径 | 说明 |
|------|------|
| `CreateProjectDialog.tsx` | 弹窗 UI |
| `../sidebar/ProjectSectionHeader.tsx` | 标题 + |
| `../../features/workspace/useCreateProjectFlow.ts` | 创建流程 + 连接校验 + 错误映射 |
| `../../features/workspace/projectCreateErrors.ts` | CONFLICT 等 → i18n |
| `../../features/workspace/projectRegistryClient.ts` | 已有 RPC 客户端 |
| `../../stores/workspaceStore.ts` | 已有 createProject / loadProjects |
