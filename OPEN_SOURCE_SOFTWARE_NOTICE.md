# OPEN SOURCE SOFTWARE NOTICE

Please note we provide an open source software notice along with this product and/or this product firmware (in the following just "this product"). The open source software licenses are granted by the respective right holders. And the open source licenses prevail all other license information with regard to the respective open source software contained in the product, including but not limited to End User Software Licensing Agreement. This notice is provided on behalf of Huawei Technologies Co. Ltd. and any of its local subsidiaries which may have provided this product to you in your local country.

## Warranty Disclaimer

THE OPEN SOURCE SOFTWARE IN THIS PRODUCT IS DISTRIBUTED IN THE HOPE THAT IT WILL BE USEFUL, BUT WITHOUT ANY WARRANTY, WITHOUT EVEN THE IMPLIED WARRANTY OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE. SEE THE APPLICABLE LICENSES FOR MORE DETAILS.

## Copyright Notice and License Texts

### Source-Referenced Components (git submodules)

The following components are referenced as git submodules and built or deployed together with this product. They are developed and licensed by their respective communities; each repository carries its own license and notice.

| Software | License | Provenance |
|---|---|---|
| yuanrong | Apache-2.0 | `https://gitcode.com/openeuler/yuanrong.git` |
| jiuwenswarm | Apache-2.0 | `https://gitcode.com/openJiuwen/jiuwenswarm.git` |
| agent-protocol | Apache-2.0 | `https://gitcode.com/openJiuwen/agent-protocol.git` |
| Conch | MulanPSL-2.0 | `https://gitcode.com/openeuler/Conch.git` |

### Third-Party System Software Installed by Deployment Scripts

The following third-party system software is downloaded and installed at deployment time by `deploy/install_deps.sh`, `deploy/etcd.sh`, and `images/Dockerfile`.

| Software | Version | License | Provenance |
|---|---:|---|---|
| MooseFS (moosefs-master / moosefs-chunkserver / moosefs-client) | 4.59.2 | GPL-2.0 | `https://repository.moosefs.com/moosefs-4/yum/el9` |
| etcd (bundled in yuanrong `third_party/etcd`) | as bundled | Apache-2.0 | `https://github.com/etcd-io/etcd` |
| Python | 3.11.x | PSF-2.0 | `https://www.python.org` |
| Node.js / npm (openEuler `nodejs` package) | repo version | MIT (Node.js License) | openEuler repository |
| Chromium (Playwright browser builds, rev 1200 / 1234) | as downloaded | BSD-3-Clause and others (Chromium License) | `https://playwright.dev` / npmmirror |
| google-noto-sans-cjk-sc-fonts | repo version | SIL OFL 1.1 | openEuler repository |
| graphviz | repo version | EPL-1.0 (with BSD parts) | openEuler repository |
| fuse3 | repo version | LGPL-2.1 | openEuler repository |

System libraries installed from the openEuler / Ubuntu repositories (nss, nspr, atk, at-spi2-atk, cups-libs, libdrm, libxkbcommon, libXcomposite, libXdamage, libXfixes, libXrandr, mesa-libgbm, libXext, libX11, pango, cairo, alsa-lib, fontconfig, freetype, libXrender, libXt, libXScrnSaver, etc.) and the `yr-runtime-sandbox` base image are licensed by their respective upstream projects under the licenses declared in the corresponding distribution packages.

### Bundled npm Runtime Packages (ppt-pipeline-swarm image)

The `images/` engine image pre-installs the following npm packages, resolved by the tracked lockfile (`images/package-lock.json`) plus two explicitly installed packages.

| Software | Version | License | Provenance |
|---|---:|---|---|
| @emnapi/runtime | 1.8.1 | MIT | npm package `@emnapi/runtime` |
| @img/colour | 1.0.0 | MIT | npm package `@img/colour` |
| @img/sharp-darwin-arm64 | 0.34.5 | Apache-2.0 | npm package `@img/sharp-darwin-arm64` |
| @img/sharp-darwin-x64 | 0.34.5 | Apache-2.0 | npm package `@img/sharp-darwin-x64` |
| @img/sharp-libvips-darwin-arm64 | 1.2.4 | LGPL-3.0-or-later | npm package `@img/sharp-libvips-darwin-arm64` |
| @img/sharp-libvips-darwin-x64 | 1.2.4 | LGPL-3.0-or-later | npm package `@img/sharp-libvips-darwin-x64` |
| @img/sharp-libvips-linux-arm | 1.2.4 | LGPL-3.0-or-later | npm package `@img/sharp-libvips-linux-arm` |
| @img/sharp-libvips-linux-arm64 | 1.2.4 | LGPL-3.0-or-later | npm package `@img/sharp-libvips-linux-arm64` |
| @img/sharp-libvips-linux-ppc64 | 1.2.4 | LGPL-3.0-or-later | npm package `@img/sharp-libvips-linux-ppc64` |
| @img/sharp-libvips-linux-riscv64 | 1.2.4 | LGPL-3.0-or-later | npm package `@img/sharp-libvips-linux-riscv64` |
| @img/sharp-libvips-linux-s390x | 1.2.4 | LGPL-3.0-or-later | npm package `@img/sharp-libvips-linux-s390x` |
| @img/sharp-libvips-linux-x64 | 1.2.4 | LGPL-3.0-or-later | npm package `@img/sharp-libvips-linux-x64` |
| @img/sharp-libvips-linuxmusl-arm64 | 1.2.4 | LGPL-3.0-or-later | npm package `@img/sharp-libvips-linuxmusl-arm64` |
| @img/sharp-libvips-linuxmusl-x64 | 1.2.4 | LGPL-3.0-or-later | npm package `@img/sharp-libvips-linuxmusl-x64` |
| @img/sharp-linux-arm | 0.34.5 | Apache-2.0 | npm package `@img/sharp-linux-arm` |
| @img/sharp-linux-arm64 | 0.34.5 | Apache-2.0 | npm package `@img/sharp-linux-arm64` |
| @img/sharp-linux-ppc64 | 0.34.5 | Apache-2.0 | npm package `@img/sharp-linux-ppc64` |
| @img/sharp-linux-riscv64 | 0.34.5 | Apache-2.0 | npm package `@img/sharp-linux-riscv64` |
| @img/sharp-linux-s390x | 0.34.5 | Apache-2.0 | npm package `@img/sharp-linux-s390x` |
| @img/sharp-linux-x64 | 0.34.5 | Apache-2.0 | npm package `@img/sharp-linux-x64` |
| @img/sharp-linuxmusl-arm64 | 0.34.5 | Apache-2.0 | npm package `@img/sharp-linuxmusl-arm64` |
| @img/sharp-linuxmusl-x64 | 0.34.5 | Apache-2.0 | npm package `@img/sharp-linuxmusl-x64` |
| @img/sharp-wasm32 | 0.34.5 | Apache-2.0 AND LGPL-3.0-or-later AND MIT | npm package `@img/sharp-wasm32` |
| @img/sharp-win32-arm64 | 0.34.5 | Apache-2.0 AND LGPL-3.0-or-later | npm package `@img/sharp-win32-arm64` |
| @img/sharp-win32-ia32 | 0.34.5 | Apache-2.0 AND LGPL-3.0-or-later | npm package `@img/sharp-win32-ia32` |
| @img/sharp-win32-x64 | 0.34.5 | Apache-2.0 AND LGPL-3.0-or-later | npm package `@img/sharp-win32-x64` |
| @nodelib/fs.scandir | 2.1.5 | MIT | npm package `@nodelib/fs.scandir` |
| @nodelib/fs.stat | 2.0.5 | MIT | npm package `@nodelib/fs.stat` |
| @nodelib/fs.walk | 1.2.8 | MIT | npm package `@nodelib/fs.walk` |
| @types/node | 22.19.3 | MIT | npm package `@types/node` |
| braces | 3.0.3 | MIT | npm package `braces` |
| core-util-is | 1.0.3 | MIT | npm package `core-util-is` |
| detect-libc | 2.1.2 | Apache-2.0 | npm package `detect-libc` |
| fast-glob | 3.3.3 | MIT | npm package `fast-glob` |
| fastq | 1.20.1 | ISC | npm package `fastq` |
| fill-range | 7.1.1 | MIT | npm package `fill-range` |
| fsevents | 2.3.2 | MIT | npm package `fsevents` |
| glob-parent | 5.1.2 | ISC | npm package `glob-parent` |
| https | 1.0.0 | ISC | npm package `https` |
| image-size | 1.2.1 | MIT | npm package `image-size` |
| immediate | 3.0.6 | MIT | npm package `immediate` |
| inherits | 2.0.4 | ISC | npm package `inherits` |
| is-extglob | 2.1.1 | MIT | npm package `is-extglob` |
| is-glob | 4.0.3 | MIT | npm package `is-glob` |
| is-number | 7.0.0 | MIT | npm package `is-number` |
| isarray | 1.0.0 | MIT | npm package `isarray` |
| jszip | 3.10.1 | (MIT OR GPL-3.0-or-later) | npm package `jszip` |
| lie | 3.3.0 | MIT | npm package `lie` |
| merge2 | 1.4.1 | MIT | npm package `merge2` |
| micromatch | 4.0.8 | MIT | npm package `micromatch` |
| minimist | 1.2.8 | MIT | npm package `minimist` |
| pako | 1.0.11 | (MIT AND Zlib) | npm package `pako` |
| picomatch | 2.3.1 | MIT | npm package `picomatch` |
| playwright | 1.57.0 | Apache-2.0 | npm package `playwright` |
| playwright-core | 1.57.0 | Apache-2.0 | npm package `playwright-core` |
| pptxgenjs | 4.0.1 | MIT | npm package `pptxgenjs` |
| process-nextick-args | 2.0.1 | MIT | npm package `process-nextick-args` |
| queue | 6.0.2 | MIT | npm package `queue` |
| queue-microtask | 1.2.3 | MIT | npm package `queue-microtask` |
| readable-stream | 2.3.8 | MIT | npm package `readable-stream` |
| reusify | 1.1.0 | MIT | npm package `reusify` |
| run-parallel | 1.2.0 | MIT | npm package `run-parallel` |
| safe-buffer | 5.1.2 | MIT | npm package `safe-buffer` |
| semver | 7.7.3 | ISC | npm package `semver` |
| setimmediate | 1.0.5 | MIT | npm package `setimmediate` |
| sharp | 0.34.5 | Apache-2.0 | npm package `sharp` |
| string_decoder | 1.1.1 | MIT | npm package `string_decoder` |
| to-regex-range | 5.0.1 | MIT | npm package `to-regex-range` |
| tslib | 2.8.1 | 0BSD | npm package `tslib` |
| undici-types | 6.21.0 | MIT | npm package `undici-types` |
| util-deprecate | 1.0.2 | MIT | npm package `util-deprecate` |
| katex | 0.18.4 | MIT | npm package `katex` (installed --no-save) |
| docx | 9.7.1 | MIT | npm package `docx` (installed --no-save) |

Note: `@img/sharp-libvips-*` binary modules are licensed under LGPL-3.0-or-later (libvips); `jszip` is dual-licensed (MIT OR GPL-3.0-or-later); `pako` is (MIT AND Zlib); `@img/sharp-wasm32` is (Apache-2.0 AND LGPL-3.0-or-later AND MIT). The image does not vendor Chromium, Firefox, or WebKit browser executables; Playwright browsers are downloaded at build time (see the Chromium row above).

### Python Runtime Dependencies

Pinned Python packages installed from `deploy/requirements.txt` and `images/Dockerfile` (exact versions are recorded in `deploy/requirements.txt`).

### License: Python Software Foundation License V2

**Software:** aiohappyeyeballs, matplotlib, typing_extensions

**PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2**

1. This LICENSE AGREEMENT is between the Python Software Foundation ("PSF"), and the Individual or Organization ("Licensee") accessing and otherwise using this software ("Python") in source or binary form and its associated documentation.
2. Subject to the terms and conditions of this License Agreement, PSF hereby grants Licensee a nonexclusive, royalty-free, world-wide license to reproduce, analyze, test, perform and/or display publicly, prepare derivative works, distribute, and otherwise use Python alone or in any derivative version, provided, however, that PSF's License Agreement and PSF's notice of copyright, i.e., "Copyright (c) 2001, 2002, 2003, 2004, 2005, 2006 Python Software Foundation; All Rights Reserved" are retained in Python alone or in any derivative version prepared by Licensee.
3. In the event Licensee prepares a derivative work that is based on or incorporates Python or any part thereof, and wants to make the derivative work available to others as provided herein, then Licensee hereby agrees to include in any such work a brief summary of the changes made to Python.
4. PSF is making Python available to Licensee on an "AS IS" basis. PSF MAKES NO REPRESENTATIONS OR WARRANTIES, EXPRESS OR IMPLIED. BY WAY OF EXAMPLE, BUT NOT LIMITATION, PSF MAKES NO AND DISCLAIMS ANY REPRESENTATION OR WARRANTY OF MERCHANTABILITY OR FITNESS FOR ANY PARTICULAR PURPOSE OR THAT THE USE OF PYTHON WILL NOT INFRINGE ANY THIRD PARTY RIGHTS.
5. PSF SHALL NOT BE LIABLE TO LICENSEE OR ANY OTHER USERS OF PYTHON FOR ANY INCIDENTAL, SPECIAL, OR CONSEQUENTIAL DAMAGES OR LOSS AS A RESULT OF MODIFYING, DISTRIBUTING, OR OTHERWISE USING PYTHON, OR ANY DERIVATIVE THEREOF, EVEN IF ADVISED OF THE POSSIBILITY THEREOF.
6. This License Agreement will automatically terminate upon a material breach of its terms and conditions.
7. Nothing in this License Agreement shall be deemed to create any relationship of agency, partnership, or joint venture between PSF and Licensee. This License Agreement does not grant permission to use PSF trademarks or trade name in a trademark sense to endorse or promote products or services of Licensee, or any third party.
8. By copying, installing or otherwise using Python, Licensee agrees to be bound by the terms and conditions of this License Agreement.

---

### License: Apache License V2.0

**Software:** Cython, PyPika, a2a-sdk, aiofiles, aiosignal, bcrypt, chromadb, courlan, cryptography, cyclopts, dashscope, diskcache, distro, fake-useragent, fastmcp, flatbuffers, frozenlist, google-adk, google-api-core, google-auth, google-genai, googleapis-common-protos, grpcio, hf-xet, htmldate, huggingface_hub, importlib_metadata, importlib_resources, jsonschema-path, kubernetes, msgpack, multidict, openai, openai-codex, openai-codex-cli-bin, opentelemetry-api, opentelemetry-exporter-otlp-proto-common, opentelemetry-exporter-otlp-proto-grpc, opentelemetry-exporter-otlp-proto-http, opentelemetry-proto, opentelemetry-sdk, opentelemetry-semantic-conventions, overrides, packaging, pathable, playwright, prometheus_client, propcache, proto-plus, py-key-value-aio, py-key-value-shared, pymilvus, pypdfium2, python-dateutil, python-multipart, python-socks, regex, requests, requests-toolbelt, safetensors, sortedcontainers, tenacity, tokenizers, trafilatura, transformers, watchdog, websocket-client, yarl

**Apache License**
**Version 2.0, January 2004**
**http://www.apache.org/licenses/**

**TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION**

**1. Definitions.**

"License" shall mean the terms and conditions for use, reproduction, and distribution as defined by Sections 1 through 9 of this document.
"Licensor" shall mean the copyright owner or entity authorized by the copyright owner that is granting the License.
"Legal Entity" shall mean the union of the acting entity and all other entities that control, are controlled by, or are under common control with that entity. For the purposes of this definition, "control" means (i) the power, direct or indirect, to cause the direction or management of such entity, whether by contract or otherwise, or (ii) ownership of fifty percent (50%) or more of the outstanding shares, or (iii) beneficial ownership of such entity.
"You" (or "Your") shall mean an individual or Legal Entity exercising permissions granted by this License.
"Source" form shall mean the preferred form for making modifications, including but not limited to software source code, documentation source, and configuration files.
"Object" form shall mean any form resulting from mechanical transformation or translation of a Source form, including but not limited to compiled object code, generated documentation, and conversions to other media types.
"Work" shall mean the work of authorship, whether in Source or Object form, made available under the License, as indicated by a copyright notice that is included in or attached to the work (an example is provided in the Appendix below).
"Derivative Works" shall mean any work, whether in Source or Object form, that is based on (or derived from) the Work and for which the editorial revisions, annotations, elaborations, or other modifications represent, as a whole, an original work of authorship. For the purposes of this License, Derivative Works shall not include works that remain separable from, or merely link (or bind by name) to the interfaces of, the Work and Derivative Works thereof.
"Contribution" shall mean any work of authorship, including the original version of the Work and any modifications or additions to that Work or Derivative Works thereof, that is intentionally submitted to Licensor for inclusion in the Work by the copyright owner or by an individual or Legal Entity authorized to submit on behalf of the copyright owner. For the purposes of this definition, "submitted" means any form of electronic, verbal, or written communication sent to the Licensor or its representatives, including but not limited to communication on electronic mailing lists, source code control systems, and issue tracking systems that are managed by, or on behalf of, the Licensor for the purpose of discussing and improving the Work, but excluding communication that is conspicuously marked or otherwise designated in writing by the copyright owner as "Not a Contribution."
"Contributor" shall mean Licensor and any individual or Legal Entity on behalf of whom a Contribution has been received by Licensor and subsequently incorporated within the Work.

**2. Grant of Copyright License.** Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to reproduce, prepare Derivative Works of, publicly display, publicly perform, sublicense, and distribute the Work and such Derivative Works in Source or Object form.

**3. Grant of Patent License.** Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable (except as stated in this section) patent license to make, have made, use, offer to sell, sell, import, and otherwise transfer the Work, where such license applies only to those patent claims licensable by such Contributor that are necessarily infringed by their Contribution(s) alone or by combination of their Contribution(s) with the Work to which such Contribution(s) was submitted. If You institute patent litigation against any entity (including a cross-claim or counterclaim in a lawsuit) alleging that the Work or a Contribution incorporated within the Work constitutes direct or contributory patent infringement, then any patent licenses granted to You under this License for that Work shall terminate as of the date such litigation is filed.

**4. Redistribution.** You may reproduce and distribute copies of the Work or Derivative Works thereof in any medium, with or without modifications, and in Source or Object form, provided that You meet the following conditions:
You must give any other recipients of the Work or Derivative Works a copy of this License; and
You must cause any modified files to carry prominent notices stating that You changed the files; and
You must retain, in the Source form of any Derivative Works that You distribute, all copyright, patent, trademark, and attribution notices from the Source form of the Work, excluding those notices that do not pertain to any part of the Derivative Works; and
If the Work includes a "NOTICE" text file as part of its distribution, then any Derivative Works that You distribute must include a readable copy of the attribution notices contained within such NOTICE file, excluding those notices that do not pertain to any part of the Derivative Works, in at least one of the following places: within a NOTICE text file distributed as part of the Derivative Works; within the Source form or documentation, if provided along with the Derivative Works; or, within a display generated by the Derivative Works, if and wherever such third-party notices normally appear. The contents of the NOTICE file are for informational purposes only and do not modify the License. You may add Your own attribution notices within Derivative Works that You distribute, alongside or as an addendum to the NOTICE text from the Work, provided that such additional attribution notices cannot be construed as modifying the License.
You may add Your own copyright statement to Your modifications and may provide additional or different license terms and conditions for use, reproduction, or distribution of Your modifications, or for any such Derivative Works as a whole, provided Your use, reproduction, and distribution of the Work otherwise complies with the conditions stated in this License.

**5. Submission of Contributions.** Unless You explicitly state otherwise, any Contribution intentionally submitted for inclusion in the Work by You to the Licensor shall be under the terms and conditions of this License, without any additional terms or conditions. Notwithstanding the above, nothing herein shall supersede or modify the terms of any separate license agreement you may have executed with Licensor regarding such Contributions.

**6. Trademarks.** This License does not grant permission to use the trade names, trademarks, service marks, or product names of the Licensor, except as required for reasonable and customary use in describing the origin of the Work and reproducing the content of the NOTICE file.

**7. Disclaimer of Warranty.** Unless required by applicable law or agreed to in writing, Licensor provides the Work (and each Contributor provides its Contributions) on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied, including, without limitation, any warranties or conditions of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A PARTICULAR PURPOSE. You are solely responsible for determining the appropriateness of using or redistributing the Work and assume any risks associated with Your exercise of permissions under this License.

**8. Limitation of Liability.** In no event and under no legal theory, whether in tort (including negligence), contract, or otherwise, unless required by applicable law (such as deliberate and grossly negligent acts) or agreed to in writing, shall any Contributor be liable to You for damages, including any direct, indirect, special, incidental, or consequential damages of any character arising as a result of this License or out of the use or inability to use the Work (including but not limited to damages for loss of goodwill, work stoppage, computer failure or malfunction, or any and all other commercial damages or losses), even if such Contributor has been advised of the possibility of such damages.

**9. Accepting Warranty or Additional Liability.** While redistributing the Work or Derivative Works thereof, You may choose to offer, and charge a fee for, acceptance of support, warranty, indemnity, or other liability obligations and/or rights consistent with this License. However, in accepting such obligations, You may act only on Your own behalf and on Your sole responsibility, not on behalf of any other Contributor, and only if You agree to indemnify, defend, and hold each Contributor harmless for any liability incurred by, or claims asserted against, such Contributor by reason of your accepting any such warranty or additional liability.

---

### License: MIT License

**Software:** Mako, PyJWT, PyYAML, SQLAlchemy, aiohttp, aiosqlite, alembic, annotated-doc, annotated-types, anthropic, anyio, attrs, backports.tarfile, beartype, beautifulsoup4, build, burner-redis, cacheout, cachetools, cffi, charset-normalizer, claude-agent-sdk, croniter, dingtalk-stream, discord.py, docstring_parser, docx2txt, durationpy, et_xmlfile, exceptiongroup, faiss-cpu, fastapi, filelock, firecrawl-anydoc, gitcode-api, graphviz, greenlet, h11, httptools, httpx-sse, installer, jaraco.classes, jaraco.context, jaraco.functools, jeepney, jiter, json-rpc, json_repair, jsonref, jsonschema, jsonschema-specifications, keyring, lark-oapi, latex2mathml, loguru, lupa, markdown-it-py, markitdown, mcp, mdurl, mermaid-py, mmh3, more-itertools, nab-index, nab-python, nab-resolver, numpy, onnxruntime, openapi-pydantic, openpyxl, orjson, pathvalidate, pdfkit, pdfminer.six, pdfplumber, pgvector, pillow, pip, pipdeptree, platformdirs, pydantic, pydantic-settings, pydantic_core, pydocket, pyoxigraph, pyproject_hooks, pysbd, python-docx, python-pptx, pytz, redis, referencing, rich, rich-rst, rpds-py, ruamel.yaml, setuptools, six, slack_bolt, slack_sdk, sniffio, socksio, soupsieve, sqlite-vec, sqlmodel, tiktoken, tomli, tomli_w, tqdm, tree-sitter, tree-sitter-bash, truststore, typer, typing-inspection, tzlocal, uncalled-for, urllib3, uvloop, watchfiles, wecom-aibot-sdk, zipp

**The MIT License**

Copyright (c) <year> <copyright holders>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

---

### License: BSD 3-Clause License

**Software:** Authlib, Jinja2, MarkupSafe, PyPDF2, PySocks, SecretStorage, babel, cloudpickle, cronsim, click, dateparser, fakeredis, fsspec, httpcore, idna, imapclient, joserfc, lxml, lxml_html_clean, markdown, oauthlib, pandas, portalocker, pyasn1_modules, pycparser, pyperclip, pypdf, protobuf, psutil, python-dotenv, reportlab, requests-oauthlib, sse-starlette, starlette, uvicorn, websockets

Copyright (c) 2007 Pallets
All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

---

### License: BSD 2-Clause License

**Software:** Pygments, pyasn1, pybase64, python-json-logger, wrapt, jusText, pycryptodome, xlsxwriter

All direct contributions to PyCryptodome are released under the following license. The copyright of each piece belongs to the respective author.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

---

### License: ISC License

**Software:** aiologic, culsans, dnspython, shellingham

Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

---

### Other Licenses

**MPL-2.0**

**Software:** certifi, tld

Full text: `https://www.mozilla.org/en-US/MPL/2.0/`

**The Unlicense**

**Software:** email-validator

Full text: `https://unlicense.org/`

**EPL-2.0 OR GPL-2.0-or-later (dual license)**

**Software:** asyncssh

Full texts: `https://www.eclipse.org/legal/epl-2.0/`, `https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt`

**GPL-2.0-or-later**

**Software:** mutagen

Full text: `https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt`

**LGPL-3.0-only**

**Software:** python-telegram-bot

Full text: `https://www.gnu.org/licenses/lgpl-3.0.txt`

**AGPL-3.0 OR Artifex Commercial License (dual license)**

**Software:** pymupdf

Full text: `https://www.gnu.org/licenses/agpl-3.0.txt`; commercial licensing available from Artifex Software. Downstream distribution must comply with the selected license terms.

**License not declared in PyPI metadata**

**Software:** a2ui-agent-sdk, openjiuwen, skillnet-ai

See the license declared in each project repository for details.

- **GPL-2.0 (MooseFS):** full text at `https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt`
- **LGPL-2.1 (fuse3):** full text at `https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt`
- **LGPL-3.0-or-later (libvips binaries in `@img/sharp-libvips-*`):** full text at `https://www.gnu.org/licenses/lgpl-3.0.txt`
- **SIL OFL 1.1 (Noto Sans CJK SC fonts):** full text at `https://openfontlicense.org/open-font-license-official-text/`
- **EPL-1.0 (graphviz):** full text at `https://www.eclipse.org/legal/epl-v10.html`
- **0BSD (tslib):** full text at `https://spdx.org/licenses/0BSD.html`

### License: Mulan Permissive Software License, Version 2 (MulanPSL-2.0)

**Software:** Conch (git submodule)

                     木兰宽松许可证, 第2版

   木兰宽松许可证， 第2版 
   2020年1月 http://license.coscl.org.cn/MulanPSL2


   您对“软件”的复制、使用、修改及分发受木兰宽松许可证，第2版（“本许可证”）的如下条款的约束：

   0. 定义

      “软件”是指由“贡献”构成的许可在“本许可证”下的程序和相关文档的集合。

      “贡献”是指由任一“贡献者”许可在“本许可证”下的受版权法保护的作品。

      “贡献者”是指将受版权法保护的作品许可在“本许可证”下的自然人或“法人实体”。

      “法人实体”是指提交贡献的机构及其“关联实体”。

      “关联实体”是指，对“本许可证”下的行为方而言，控制、受控制或与其共同受控制的机构，此处的控制是指有受控方或共同受控方至少50%直接或间接的投票权、资金或其他有价证券。

   1. 授予版权许可

      每个“贡献者”根据“本许可证”授予您永久性的、全球性的、免费的、非独占的、不可撤销的版权许可，您可以复制、使用、修改、分发其“贡献”，不论修改与否。

   2. 授予专利许可

      每个“贡献者”根据“本许可证”授予您永久性的、全球性的、免费的、非独占的、不可撤销的（根据本条规定撤销除外）专利许可，供您制造、委托制造、使用、许诺销售、销售、进口其“贡献”或以其他方式转移其“贡献”。前述专利许可仅限于“贡献者”现在或将来拥有或控制的其“贡献”本身或其“贡献”与许可“贡献”时的“软件”结合而将必然会侵犯的专利权利要求，不包括对“贡献”的修改或包含“贡献”的其他结合。如果您或您的“关联实体”直接或间接地，就“软件”或其中的“贡献”对任何人发起专利侵权诉讼（包括反诉或交叉诉讼）或其他专利维权行动，指控其侵犯专利权，则“本许可证”授予您对“软件”的专利许可自您提起诉讼或发起维权行动之日终止。

   3. 无商标许可

      “本许可证”不提供对“贡献者”的商品名称、商标、服务标志或产品名称的商标许可，但您为满足第4条规定的声明义务而必须使用除外。

   4. 分发限制

      您可以在任何媒介中将“软件”以源程序形式或可执行形式重新分发，不论修改与否，但您必须向接收者提供“本许可证”的副本，并保留“软件”中的版权、商标、专利及免责声明。

   5. 免责声明与责任限制

      “软件”及其中的“贡献”在提供时不带任何明示或默示的担保。在任何情况下，“贡献者”或版权所有者不对任何人因使用“软件”或其中的“贡献”而引发的任何直接或间接损失承担责任，不论因何种原因导致或者基于何种法律理论，即使其曾被建议有此种损失的可能性。 

   6. 语言
      “本许可证”以中英文双语表述，中英文版本具有同等法律效力。如果中英文版本存在任何冲突不一致，以中文版为准。

   条款结束 

   如何将木兰宽松许可证，第2版，应用到您的软件
   
   如果您希望将木兰宽松许可证，第2版，应用到您的新软件，为了方便接收者查阅，建议您完成如下三步：

      1， 请您补充如下声明中的空白，包括软件名、软件的首次发表年份以及您作为版权人的名字；

      2， 请您在软件包的一级目录下创建以“LICENSE”为名的文件，将整个许可证文本放入该文件中；

      3， 请将如下声明文本放入每个源文件的头部注释中。

   Copyright (c) [Year] [name of copyright holder]
   [Software Name] is licensed under Mulan PSL v2.
   You can use this software according to the terms and conditions of the Mulan PSL v2. 
   You may obtain a copy of Mulan PSL v2 at:
            http://license.coscl.org.cn/MulanPSL2 
   THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.  
   See the Mulan PSL v2 for more details.  


                     Mulan Permissive Software License，Version 2

   Mulan Permissive Software License，Version 2 (Mulan PSL v2)
   January 2020 http://license.coscl.org.cn/MulanPSL2

   Your reproduction, use, modification and distribution of the Software shall be subject to Mulan PSL v2 (this License) with the following terms and conditions: 
   
   0. Definition
   
      Software means the program and related documents which are licensed under this License and comprise all Contribution(s). 
   
      Contribution means the copyrightable work licensed by a particular Contributor under this License.
   
      Contributor means the Individual or Legal Entity who licenses its copyrightable work under this License.
   
      Legal Entity means the entity making a Contribution and all its Affiliates.
   
      Affiliates means entities that control, are controlled by, or are under common control with the acting entity under this License, ‘control’ means direct or indirect ownership of at least fifty percent (50%) of the voting power, capital or other securities of controlled or commonly controlled entity.

   1. Grant of Copyright License

      Subject to the terms and conditions of this License, each Contributor hereby grants to you a perpetual, worldwide, royalty-free, non-exclusive, irrevocable copyright license to reproduce, use, modify, or distribute its Contribution, with modification or not.

   2. Grant of Patent License 

      Subject to the terms and conditions of this License, each Contributor hereby grants to you a perpetual, worldwide, royalty-free, non-exclusive, irrevocable (except for revocation under this Section) patent license to make, have made, use, offer for sale, sell, import or otherwise transfer its Contribution, where such patent license is only limited to the patent claims owned or controlled by such Contributor now or in future which will be necessarily infringed by its Contribution alone, or by combination of the Contribution with the Software to which the Contribution was contributed. The patent license shall not apply to any modification of the Contribution, and any other combination which includes the Contribution. If you or your Affiliates directly or indirectly institute patent litigation (including a cross claim or counterclaim in a litigation) or other patent enforcement activities against any individual or entity by alleging that the Software or any Contribution in it infringes patents, then any patent license granted to you under this License for the Software shall terminate as of the date such litigation or activity is filed or taken.

   3. No Trademark License

      No trademark license is granted to use the trade names, trademarks, service marks, or product names of Contributor, except as required to fulfill notice requirements in Section 4.

   4. Distribution Restriction

      You may distribute the Software in any medium with or without modification, whether in source or executable forms, provided that you provide recipients with a copy of this License and retain copyright, patent, trademark and disclaimer statements in the Software.

   5. Disclaimer of Warranty and Limitation of Liability

      THE SOFTWARE AND CONTRIBUTION IN IT ARE PROVIDED WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED. IN NO EVENT SHALL ANY CONTRIBUTOR OR COPYRIGHT HOLDER BE LIABLE TO YOU FOR ANY DAMAGES, INCLUDING, BUT NOT LIMITED TO ANY DIRECT, OR INDIRECT, SPECIAL OR CONSEQUENTIAL DAMAGES ARISING FROM YOUR USE OR INABILITY TO USE THE SOFTWARE OR THE CONTRIBUTION IN IT, NO MATTER HOW IT’S CAUSED OR BASED ON WHICH LEGAL THEORY, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

   6. Language

      THIS LICENSE IS WRITTEN IN BOTH CHINESE AND ENGLISH, AND THE CHINESE VERSION AND ENGLISH VERSION SHALL HAVE THE SAME LEGAL EFFECT. IN THE CASE OF DIVERGENCE BETWEEN THE CHINESE AND ENGLISH VERSIONS, THE CHINESE VERSION SHALL PREVAIL.

   END OF THE TERMS AND CONDITIONS

   How to Apply the Mulan Permissive Software License，Version 2 (Mulan PSL v2) to Your Software

      To apply the Mulan PSL v2 to your work, for easy identification by recipients, you are suggested to complete following three steps:

      i Fill in the blanks in following statement, including insert your software name, the year of the first publication of your software, and your name identified as the copyright owner; 

      ii Create a file named “LICENSE” which contains the whole context of this License in the first directory of your software package;

      iii Attach the statement to the appropriate annotated syntax at the beginning of each source file.


   Copyright (c) [Year] [name of copyright holder]
   [Software Name] is licensed under Mulan PSL v2.
   You can use this software according to the terms and conditions of the Mulan PSL v2. 
   You may obtain a copy of Mulan PSL v2 at:
               http://license.coscl.org.cn/MulanPSL2 
   THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.  
   See the Mulan PSL v2 for more details.

---

*This notice is generated for the AgentOS project. The list of software and versions may vary with the actual installation. You may regenerate the Python dependency list using `pip install pip-licenses; pip-licenses` and the npm dependency list using `npm ls --all --json` from the project environment.*
