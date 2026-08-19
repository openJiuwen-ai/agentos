# MooseFS 依赖包安装说明

MooseFS 部署脚本（`moosefs_deploy.sh`）不负责包的下载和安装。包需由上游流程预先安装。本文档列出不同操作系统所需的依赖包及安装方法。

## 支持的操作系统

| 操作系统 | 版本 | 架构 | 包格式 |
|---------|------|------|--------|
| openEuler | 22.03-LTS-SP1/SP4 | x86_64, aarch64 | RPM |
| openEuler | 24.03-LTS-SP1/SP4 | x86_64, aarch64 | RPM |
| Ubuntu | 22.04 (Jammy) | amd64, arm64 | DEB |
| Ubuntu | 24.04 (Noble) | amd64, arm64 | DEB |

## MooseFS 包列表（版本 4.59.2）

| 包名 | 说明 |
|------|------|
| `moosefs-master` | 元数据服务器 |
| `moosefs-chunkserver` | 数据块服务器 |
| `moosefs-client` | FUSE 客户端 (mfsmount) |

此外还需安装 `fuse3`（提供 `libfuse3.so.3`，moosefs-client 依赖）。

---

## openEuler 安装

### MooseFS RPM 包获取

MooseFS 官方 RPM 源：`https://repository.moosefs.com/moosefs-4/yum/el9/`

**方式一：配置 yum 源（推荐，可后续 dnf 直接安装/升级）**

```bash
cat > /etc/yum.repos.d/moosefs.repo << 'EOF'
[moosefs]
name=MooseFS 4
baseurl=https://repository.moosefs.com/moosefs-4/yum/el9/$basearch/
gpgcheck=0
enabled=1
EOF
dnf clean all && dnf makecache
```

**方式二：wget 直接下载 RPM 包**

```bash
# <arch> 替换为 x86_64 或 aarch64
ARCH=<arch>
BASE_URL=https://repository.moosefs.com/moosefs-4/yum/el9/${ARCH}

wget ${BASE_URL}/moosefs-master-4.59.2-1.rhsystemd.${ARCH}.rpm
wget ${BASE_URL}/moosefs-chunkserver-4.59.2-1.rhsystemd.${ARCH}.rpm
wget ${BASE_URL}/moosefs-client-4.59.2-1.rhsystemd.${ARCH}.rpm
```

### fuse3 包获取

| openEuler 版本 | fuse3 包名格式 | 下载源 |
|----------------|---------------|--------|
| 22.03-LTS-SP1 | `fuse3-*.oe2203sp1.<arch>.rpm` | openEuler 官方 everything 仓库 |
| 22.03-LTS-SP4 | `fuse3-3.10.5-9.oe2203sp4.<arch>.rpm` | openEuler 官方 everything 仓库 |
| 24.03-LTS-SP1 | `fuse3-*.oe2403sp1.<arch>.rpm` | openEuler 官方 everything 仓库 |
| 24.03-LTS-SP4 | `fuse3-3.16.2-3.oe2403sp4.<arch>.rpm` | openEuler 官方 everything 仓库 |

```bash
# 方式一：dnf 直接安装（系统已配置 openEuler 官方源）
dnf install -y fuse3

# 方式二：wget 下载后安装（<arch> 替换为 x86_64 或 aarch64）
# 22.03-SP1: https://dl-cdn.openeuler.openatom.cn/openEuler-22.03-LTS-SP1/everything/<arch>/Packages/
# 22.03-SP4: https://dl-cdn.openeuler.openatom.cn/openEuler-22.03-LTS-SP4/everything/<arch>/Packages/
# 24.03-SP1: https://dl-cdn.openeuler.openatom.cn/openEuler-24.03-LTS-SP1/everything/<arch>/Packages/
# 24.03-SP4: https://dl-cdn.openeuler.openatom.cn/openEuler-24.03-LTS-SP4/everything/<arch>/Packages/
wget <fuse3_url>
rpm -ivh fuse3-*.rpm
```

### 安装命令

```bash
# 安装 fuse3
dnf install -y fuse3 || rpm -ivh fuse3-*.rpm

# 安装 MooseFS（--nodeps 跳过 MooseFS 内部依赖检查，避免 fuse3 版本号不匹配）
rpm -ivh --nodeps \
  moosefs-master-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-chunkserver-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-client-4.59.2-1.rhsystemd.<arch>.rpm
```

> `<arch>` 替换为 `x86_64` 或 `aarch64`。

### 各版本对应关系

| openEuler 版本 | glibc | MooseFS 源 | RPM 包后缀 |
|----------------|-------|-----------|-----------|
| 22.03-LTS-SP1 | 2.34 | `el9/` | `rhsystemd.<arch>` |
| 22.03-LTS-SP4 | 2.34 | `el9/` | `rhsystemd.<arch>` |
| 24.03-LTS-SP1 | 2.38 | `el9/` | `rhsystemd.<arch>` |
| 24.03-LTS-SP4 | 2.38 | `el9/` | `rhsystemd.<arch>` |

> 24.03 虽然使用 glibc 2.38，但 `el9/` 的 RPM 兼容。

---

## Ubuntu 安装

### MooseFS DEB 包获取

MooseFS 官方 DEB 源：`https://repository.moosefs.com/moosefs-4/apt/ubuntu/`

| Ubuntu 版本 | 代号 | DEB 源路径 |
|-------------|------|-----------|
| 22.04 | Jammy | `apt/ubuntu/jammy/pool/main/m/moosefs/` |
| 24.04 | Noble | `apt/ubuntu/noble/pool/main/m/moosefs/` |

**方式一：配置 apt 源（推荐，可后续 apt 直接安装/升级）**

```bash
# 安装 GPG key
wget -O - https://repository.moosefs.com/moosefs.com.key | gpg --dearmor -o /usr/share/keyrings/moosefs.gpg

# <codename> 替换为 jammy 或 noble
cat > /etc/apt/sources.list.d/moosefs.list << EOF
deb [signed-by=/usr/share/keyrings/moosefs.gpg] https://repository.moosefs.com/moosefs-4/apt/ubuntu <codename> main
EOF

apt-get update
```

**方式二：wget 直接下载 DEB 包**

```bash
# <arch> 替换为 amd64 或 arm64
# <codename> 替换为 jammy 或 noble
ARCH=<arch>
CODENAME=<codename>
BASE_URL=https://repository.moosefs.com/moosefs-4/apt/ubuntu/${CODENAME}/pool/main/m/moosefs

wget ${BASE_URL}/moosefs-master_4.59.2-1_${ARCH}.deb
wget ${BASE_URL}/moosefs-chunkserver_4.59.2-1_${ARCH}.deb
wget ${BASE_URL}/moosefs-client_4.59.2-1_${ARCH}.deb
```

### fuse3 包获取

Ubuntu 官方仓库自带 fuse3，无需额外配置下载源：

```bash
apt-get update && apt-get install -y fuse3
```

### 安装命令

```bash
# 安装 fuse3
apt-get update && apt-get install -y fuse3

# 安装 MooseFS（--force-depends 跳过依赖检查）
dpkg -i --force-depends \
  moosefs-master_4.59.2-1_<arch>.deb \
  moosefs-chunkserver_4.59.2-1_<arch>.deb \
  moosefs-client_4.59.2-1_<arch>.deb
```

> `<arch>` 替换为 `amd64` 或 `arm64`。

### DEB 包名格式

```
moosefs-master_4.59.2-1_<arch>.deb
moosefs-chunkserver_4.59.2-1_<arch>.deb
moosefs-client_4.59.2-1_<arch>.deb
```

---

## 升级已安装的包

### RPM (openEuler)

```bash
# 方式一：配置了 yum 源
dnf upgrade moosefs-master moosefs-chunkserver moosefs-client

# 方式二：手动下载 RPM
rpm -Uvh --force \
  moosefs-master-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-chunkserver-4.59.2-1.rhsystemd.<arch>.rpm \
  moosefs-client-4.59.2-1.rhsystemd.<arch>.rpm
```

### DEB (Ubuntu)

```bash
# 方式一：配置了 apt 源
apt-get upgrade moosefs-master moosefs-chunkserver moosefs-client

# 方式二：手动下载 DEB
dpkg -i --force-depends \
  moosefs-master_4.59.2-1_<arch>.deb \
  moosefs-chunkserver_4.59.2-1_<arch>.deb \
  moosefs-client_4.59.2-1_<arch>.deb
```

---

## 验证安装

### RPM (openEuler)

```bash
rpm -q moosefs-master moosefs-chunkserver moosefs-client
rpm -q fuse3
```

### DEB (Ubuntu)

```bash
dpkg -s moosefs-master moosefs-chunkserver moosefs-client | grep Status
dpkg -s fuse3 | grep Status
```

全部确认已安装后，执行部署脚本：

```bash
bash deploy/moosefs/moosefs_deploy.sh install
bash deploy/moosefs/moosefs_deploy.sh up
```
