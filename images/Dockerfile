# ============================================================
# ppt-pipeline-swarm runtime —— 预装全部运行依赖
# 基础镜像: yr-runtime-sandbox:latest (openEuler, aarch64, py3.11)
# 交付: npm引擎依赖->/opt/html2pptx/node_modules
#       python包->/usr/local/lib/python3.11/site-packages
#       playwright->/root/.cache/ms-playwright (rev 1200/1234)
# ============================================================
FROM swr.cn-southwest-2.myhuaweicloud.com/yuanrong-dev/yr-runtime-sandbox:latest

# 构建期环境（免校验自签名证书）
ENV GIT_SSL_NO_VERIFY=true \
    PLAYWRIGHT_BROWSERS_PATH=/tmp/ms-playwright

# 1) 系统依赖: nodejs/npm + chromium 运行库 (openEuler 仓库自签名, 需 sslverify=0)
RUN printf '[main]\nsslverify=0\n' > /etc/dnf/dnf.conf && \
    dnf -y install nodejs nss nspr atk at-spi2-atk cups-libs libdrm \
        libxkbcommon libXcomposite libXdamage libXfixes libXrandr \
        mesa-libgbm libXext libX11 pango cairo alsa-lib fontconfig \
        freetype libXrender libXt libXScrnSaver findutils findutils-find && \
    dnf clean all

# 2) npm 引擎依赖: npm ci 按 lock 精确安装 (走华为云 npm 镜像)
WORKDIR /opt/html2pptx
COPY package.json ./
COPY package-lock.json ./
RUN npm config set strict-ssl false && \
    npm ci --registry=https://mirrors.huaweicloud.com/repository/npm/ && \
    npm cache clean --force

# 3) Playwright Chromium (rev 1234): 用 python 脚本直连 npmmirror 下载
COPY download_playwright_browsers.py /usr/local/bin/download_playwright_browsers.py
RUN python3 /usr/local/bin/download_playwright_browsers.py && \
    rm -f /usr/local/bin/download_playwright_browsers.py

# 4) Python 依赖 (直连 pypi 官方源; pip 需信任 pypi 的 SSL)
RUN pip3 config set global.index-url https://pypi.org/simple && \
    pip3 install \
        python-pptx requests pypdf pdfplumber pymupdf \
        playwright markitdown markdown-it-py Pillow fake-useragent && \
    pip3 cache purge && \
    pip3 config unset global.index-url

# 5) 校验: python 包可导入 + node chromium 可启动
RUN python3 -c "import pptx, fitz, pypdf, pdfplumber, playwright, PIL, markitdown, markdown_it, fake_useragent; print('python-deps OK')" && \
    node -e "const {chromium}=require('/opt/html2pptx/node_modules/playwright'); \
      chromium.launch({headless:true}).then(b=>{console.log('chromium OK'); return b.close()}).catch(e=>{console.error(e.message); process.exit(1)})"

WORKDIR /
