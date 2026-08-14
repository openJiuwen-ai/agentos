# MooseFS 依赖包安装说明

MooseFS 部署脚本（`moosefs_deploy.sh`）不负责 RPM 包的下载和安装。RPM 包需由上游流程预先安装。本文档列出不同 openEuler 版本和架构所需的依赖包及安装方法。

## MooseFS 官方源结构

MooseFS 官方源地址：`https://repository.moosefs.com/moosefs-4/yum/`

| 目录 | 架构 | 包后缀 | 对应 glibc |
|------|------|--------|-----------|
| `el9/` | x86_64, aarch64 | `rhsystemd` | glibc 2.34 |
| `el10/` | x86_64, aarch64 | `rhsystemd` | glibc 2.38 |

## openEuler 版本与 MooseFS 源对应关系

| openEuler 版本 | glibc 版本 | 架构 | MooseFS 源 | RPM 包后缀 |
|----------------|-----------|------|-----------|-----------|
| 22.03-LTS-SP1 | 2.34 | x86_64 | `el9/` | `rhsystemd.x86_64` |
| 22.03-LTS-SP1 | 2.34 | aarch64 | `el9/` | `rhsystemd.aarch64` |
| 22.03-LTS-SP4 | 2.34 | x86_64 | `el9/` | `rhsystemd.x86_64` |
| 22.03-LTS-SP4 | 2.34 | aarch64 | `el9/` | `rhsystemd.aarch64` |
| 24.03-LTS-SP1 | 2.38 | x86_64 | `el9/` | `rhsystemd.x86_64` |
| 24.03-LTS-SP1 | 2.38 | aarch64 | `el9/` | `rhsystemd.aarch64` |
| 24.03-LTS-SP4 | 2.38 | x86_64 | `el9/` | `rhsystemd.x86_64` |
| 24.03-LTS-SP4 | 2.38 | aarch64 | `el9/` | `rhsystemd.aarch64` |

## MooseFS RPM 包列表（版本 4.59.2）

| 包名 | 说明 |
|------|------|
| `moosefs-master-4.59.2-1.rhsystemd.<arch>.rpm` | 元数据服务器 |
| `moosefs-chunkserver-4.59.2-1.rhsystemd.<arch>.rpm` | 数据块服务器 |
| `moosefs-client-4.59.2-1.rhsystemd.<arch>.rpm` | FUSE 客户端 (mfsmount) |

`<arch>` 为 `x86_64` 或 `aarch64`。

## fuse3 依赖

`moosefs-client` 依赖 `libfuse3.so.3`，需安装 `fuse3` 包。各 openEuler 版本的 fuse3 包名不同：

| openEuler 版本 | fuse3 包名格式 |
|----------------|---------------|
| 22.03-LTS-SP1 | `fuse3-*.oe2203sp1.<arch>.rpm` |
| 22.03-LTS-SP4 | `fuse3-3.10.5-9.oe2203sp4.<arch>.rpm` |
| 24.03-LTS-SP1 | `fuse3-*.oe2403sp1.<arch>.rpm` |
| 24.03-LTS-SP4 | `fuse3-3.16.2-3.oe2403sp4.<arch>.rpm` |

## 按操作系统安装

> 以下命令中 `<arch>` 替换为实际架构（`x86_64` 或 `aarch64`）。

### openEuler 22.03-LTS-SP1

```bash
# MooseFS 下载源：https://repository.moosefs.com/moosefs-4/yum/el9/
# fuse3 下载源：https://dl-cdn.openeuler.openatom.cn/openEuler-22.03-LTS-SP1/everything/<arch>/Packages/

# 安装 fuse3
dnf install -y fuse3 || rpm -ivh fuse3-*.oe2203sp1.<arch>.rpm

# 安装 MooseFS
rpm -ivh --nodeps \
  moosefs-master-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-chunkserver-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-client-4.59.2-1.rhsystemd.<arch>.rpm
```

### openEuler 22.03-LTS-SP4

```bash
# MooseFS 下载源：https://repository.moosefs.com/moosefs-4/yum/el9/
# fuse3 下载源：https://dl-cdn.openeuler.openatom.cn/openEuler-22.03-LTS-SP4/everything/<arch>/Packages/

# 安装 fuse3
dnf install -y fuse3 || rpm -ivh fuse3-3.10.5-9.oe2203sp4.<arch>.rpm

# 安装 MooseFS
rpm -ivh --nodeps \
  moosefs-master-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-chunkserver-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-client-4.59.2-1.rhsystemd.<arch>.rpm
```

### openEuler 24.03-LTS-SP1

```bash
# MooseFS 下载源：https://repository.moosefs.com/moosefs-4/yum/el9/
# fuse3 下载源：https://dl-cdn.openeuler.openatom.cn/openEuler-24.03-LTS-SP1/everything/<arch>/Packages/

# 安装 fuse3
dnf install -y fuse3 || rpm -ivh fuse3-*.oe2403sp1.<arch>.rpm

# 安装 MooseFS
rpm -ivh --nodeps \
  moosefs-master-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-chunkserver-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-client-4.59.2-1.rhsystemd.<arch>.rpm
```

### openEuler 24.03-LTS-SP4

```bash
# MooseFS 下载源：https://repository.moosefs.com/moosefs-4/yum/el9/
# fuse3 下载源：https://dl-cdn.openeuler.openatom.cn/openEuler-24.03-LTS-SP4/everything/<arch>/Packages/

# 安装 fuse3
dnf install -y fuse3 || rpm -ivh fuse3-3.16.2-3.oe2403sp4.<arch>.rpm

# 安装 MooseFS
rpm -ivh --nodeps \
  moosefs-master-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-chunkserver-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-client-4.59.2-1.rhsystemd.<arch>.rpm
```

## 升级已安装的包

如 MooseFS 已安装需升级：

```bash
rpm -Uvh --force \
  moosefs-master-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-chunkserver-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-client-4.59.2-1.rhsystemd.<arch>.rpm
```

## 验证安装

```bash
# 验证 MooseFS 包
rpm -q moosefs-master moosefs-chunkserver moosefs-client

# 验证 fuse3
rpm -q fuse3
```

全部确认已安装后，执行部署脚本：

```bash
bash deploy/moosefs/moosefs_deploy.sh install
bash deploy/moosefs/moosefs_deploy.sh up
```
