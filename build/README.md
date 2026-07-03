# AgentOS 构建说明

`build.sh` 用于下载 JiuwenSwarm、openYuanrong 发布包，并与 `deploy/` 目录一起打包为可分发的 tar 包。

## 前置条件

- Bash
- `curl` 或 `wget`（用于下载发布包）
- 可访问外网（gitcode.com、华为云 OBS）

## 使用方法

在仓库根目录或 `build/` 目录下执行：

```bash
./build/build.sh
```

或：

```bash
cd build && ./build.sh
```

## 构建流程

脚本按以下顺序执行：

| 步骤 | 函数 | 说明 |
|------|------|------|
| 1 | `clean` | 清理 `build/dist/` 及中间产物 |
| 2 | `build_manager_app` | 预留步骤（当前为空） |
| 3 | `build_jiuwenswarm` | 下载 JiuwenSwarm 发布包 |
| 4 | `build_openyuanrong` | 下载 openYuanrong 发布包（linux/aarch64） |
| 5 | `build_conch` | 预留步骤（当前为空） |
| 6 | `pack` | 打包生成 `AgentOS-Client.tgz` 与 `AgentOS-Server.tgz` |

任一步骤失败时，脚本会因 `set -e` 立即退出。

## 下载内容

### JiuwenSwarm（版本 0.2.2）

来源：`https://gitcode.com/openJiuwen/jiuwenswarm/releases/download/JiuwenSwarm0.2.2/`

| 文件 | 用途 |
|------|------|
| `jiuwenswarm-0.2.2-py3-none-any.whl` | 服务端通用包 |
| `jiuwenswarm_tui-0.2.2-py3-none-macosx_11_0_arm64.whl` | macOS ARM64 客户端 TUI |
| `jiuwenswarm_tui-0.2.2-py3-none-win_amd64.whl` | Windows 客户端 TUI |

### openYuanrong（版本 0.8.0，linux/aarch64）

来源：`https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/release/0.8.0/linux/aarch64/`

| 文件 |
|------|
| `openyuanrong_functionsystem-0.8.0-py3-none-manylinux_2_34_aarch64.whl` |
| `openyuanrong-0.8.0-cp311-cp311-manylinux_2_34_aarch64.whl` |
| `openyuanrong_datasystem-0.8.0-cp311-cp311-manylinux_2_34_aarch64.whl` |
| `openyuanrong_faas-0.8.0-cp311-cp311-manylinux_2_34_aarch64.whl` |
| `openyuanrong_runtime-0.8.0-cp311-cp311-manylinux_2_34_aarch64.whl` |

下载文件保存在：

```
build/dist/downloads/jiuwenswarm/
build/dist/downloads/openyuanrong/
```

已存在的文件会跳过下载（输出 `skip (exists)`）。

## 输出产物

产物位于 `build/dist/`：

### `AgentOS-Client.tgz`

客户端安装包，包含两个 TUI wheel：

- `jiuwenswarm_tui-0.2.2-py3-none-macosx_11_0_arm64.whl`
- `jiuwenswarm_tui-0.2.2-py3-none-win_amd64.whl`

### `AgentOS-Server.tgz`

服务端安装包（aarch64），包含：

- `jiuwenswarm-0.2.2-py3-none-any.whl`
- 上述 5 个 openYuanrong wheel
- `deploy/` 目录（来自仓库 `deploy/`）

## 目录结构示例

构建完成后：

```
build/
├── build.sh
├── README.md
└── dist/
    ├── AgentOS-Client.tgz
    ├── AgentOS-Server.tgz
    ├── downloads/
    │   ├── jiuwenswarm/
    │   └── openyuanrong/
    └── staging/          # 打包中间目录，可忽略
        ├── client/
        └── server/
```

`build/dist/` 已加入 `.gitignore`，不会提交到 Git。

## 下载失败时的报错

下载失败时终端会输出：

1. 正在下载的文件名与 URL
2. `curl` / `wget` 的原始错误（如 HTTP 404、超时）
3. 脚本汇总信息：`error: failed to download <文件名>` 及对应 `url:`

若下载到空文件，会报：`error: downloaded file is empty: <文件名>`。

失败时不会保留损坏的 `.part` 临时文件。

## 常见问题

**怀疑本地 wheel 已损坏，想重新下载**

删除对应文件或整个 `build/dist/` 后重新执行 `./build.sh`（脚本开头会 `clean` 整个 `build/dist/`）。

**打包时报 `deploy directory not found`**

确认仓库根目录存在 `deploy/` 目录。

**修改依赖版本**

在 `build.sh` 顶部修改 `JIUWENSWARM_VERSION`、`OPENYUANRONG_VERSION` 及对应包列表。
