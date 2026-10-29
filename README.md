# 梦星截屏 · 录屏与离线翻译

Windows 桌面工具：**截图标注 + 屏幕录制 + 截图 OCR 翻译**，全部在本机运行，
不上传任何数据。翻译同时支持两种离线引擎：内置 Argos 本地模型、以及可选的 Ollama 本地大模型。

作者：詹康明　·　GitHub：<https://github.com/MengXingXiaoMing/mengxing-capture>

---

## 一、功能

**一个入口搞定**
截图、截图翻译、区域录屏共用同一个框选流程：按 `Ctrl + Alt + A` 拉框后，
在下方工具栏直接选择「复制 / 保存 / 翻译 / 录屏」，不用记多个快捷键。

**截图**
- 全局快捷键唤起，全屏框选（支持多显示器）
- 框选后选框一直显示：8 个控制点可拖动改变大小，也可在框内拖动整体移动，尺寸标签常驻
- 标注：矩形、椭圆、箭头、画笔、高亮、马赛克、文字、序号
- 撤销、重新框选、复制到剪贴板、保存为 PNG/JPG
- 高 DPI（125% / 150% / 200% 缩放）下坐标与清晰度均按物理像素处理

**文本翻译**
- 「翻译」页顶部可直接输入文字翻译，像在线翻译一样使用
- 自动检测原文语言，也可手动指定；`⇄` 一键互换源语言与目标语言
- `Ctrl + Enter` 快速提交，支持多行文本，一键复制译文

**截图翻译**
- 框选屏幕文字 → 离线 OCR（RapidOCR / ONNX Runtime）→ 识别结果直接填进「翻译」页输入框并自动翻译
- 不会弹出额外窗口：结果就显示在主界面的译文区，识别错了可以直接在输入框里改，再点「翻译」
- 自动识别原文语言；顶部可以手动修改「从」「到」语言，中间 `⇄` 一键互换
- 两种引擎可切换：Argos 本地模型（体积小、速度快）、Ollama 本地大模型（质量更好）

**录屏**
- 区域 / 全屏 / 指定窗口
- 录制期间屏幕上常驻橙色区域指示框（暂停时变黄），鼠标可穿透，且边框画在录制区域之外、不会被录进视频
- 暂停与继续（自动分段录制后无损合并）
- 系统声音通过 WASAPI 回环直接采集扬声器输出，**不需要「立体声混音」或虚拟声卡**
- 可同时录制麦克风并与系统声音混音
- 摄像头画中画（四角可选、大小可调）
- 导出 MP4（H.264 + AAC），在「设置 → 最近生成」里右键可导出 GIF

**系统集成**
- 全局快捷键、系统托盘常驻、托盘菜单快捷操作
- 关闭窗口后仍在后台，热键随时可用

---

## 二、快速开始

### 方式 A：直接运行源码（开发/调试）

要求：Windows 10/11、Python 3.10 – 3.12（推荐 3.11）。

**最简单：双击根目录的 `梦星截屏` 快捷方式**

- 快捷方式带应用图标，只保留这一个启动入口
- 会使用项目内的 `.venv`，启动后不保留黑色命令行窗口
- 首次换电脑没有 `.venv` 时，运行 `build\first_run_setup.bat` 自动安装依赖
- 界面打不开或闪退时，运行 `build\run_console.bat`，控制台会停在错误信息上

手动执行：

```bat
:: 1. 创建独立环境（不会影响系统 Python）
python -m venv .venv

:: 2. 安装依赖
.venv\Scripts\python.exe -m pip install -r requirements.txt

:: 3. 启动
build\run_console.bat
```

`build\run_console.bat` 会优先使用项目内的 `.venv`，找不到时才回退到系统 Python。

环境自检（不弹主界面，只打印依赖与抓屏状态）：

```bat
.venv\Scripts\python.exe main.py --self-test
```

### 方式 B：便携版 exe（推荐给普通使用）

在一台有网络的电脑上构建一次，得到完全独立的文件夹，拷到任何 Windows 机器双击即用，
**不需要安装 Python，不写注册表，不改系统环境**：

```powershell
powershell -ExecutionPolicy Bypass -File build\build_portable.ps1 -WithModels -WithOllama -Zip
```

产物：`dist\MengXingCapture\`（含 Python 运行时、PyQt6、OCR 模型、ffmpeg、Argos 语言包、
以及 `vendor\ollama` 里的 Ollama 安装包与模型），以及 `dist\MengXingCapture-portable.zip`。

- `-WithModels`：打包已下载的 Argos 语言包（`userdata\models\argos\packages`）
- `-WithOllama`：打包 `vendor\ollama`（安装包 + 模型），离线电脑可直接装

- 双击 `MengXingCapture.exe` 或 `Start.bat` 启动
- 所有数据都写在程序目录的 `userdata\` 下，删掉文件夹即彻底卸载

### 方式 C：无网络的电脑（离线安装包）

1. 在有网络的机器上准备依赖包：

```powershell
powershell -ExecutionPolicy Bypass -File build\build_offline_wheels.ps1 -DownloadPython -Zip
```

   会生成 `vendor\wheels\`（全部 wheel 文件）与 `vendor\python\`（Python 安装器，可选）。

2. 把整个项目目录（或生成的 zip）拷贝到离线电脑。
3. 若目标机器没有 Python，先运行 `vendor\python\python-3.11.9-amd64.exe` 安装。
4. 双击 `build\install_offline.bat`：自动创建项目内 `.venv` 并从 `vendor\wheels` 离线安装，随后启动。

> 便携版（方式 B）本身已经是离线可用的，只是需要在有网机器上构建。
> 如果连构建环境都没有，用方式 C 在目标机器本地安装依赖。

---

## 三、快捷键

| 功能 | 默认快捷键 |
| --- | --- |
| 截图 | `Ctrl + Alt + A` |
| 截图翻译 | `Ctrl + Alt + T` |
| 开始 / 停止录屏 | `Ctrl + Alt + R` |
| 暂停 / 继续录屏 | `Ctrl + Alt + P` |
| 停止录屏 | `Ctrl + Alt + S` |

所有快捷键都可以在「设置」中点击输入框后直接按键修改。若被其它软件占用，
保存时会提示冲突，换一个组合键即可。

截图遮罩内的操作：

- 拖动框选，松手进入标注
- `Enter` 复制并关闭，`Ctrl + C` 复制，`Ctrl + S` 保存，`Ctrl + Z` 撤销
- `Esc` 返回重新框选，再按一次退出；右键同样可以退出

---

## 四、离线翻译

### Argos 本地模型（默认，推荐）

- 组件：CTranslate2 + SentencePiece，直接读取官方 `.argosmodel` 语言包
  （包里自带的 stanza 分词模型会被跳过，节省约 15MB）
- 首次使用需要联网下载一次语言包，之后**完全离线**
- 官方索引里**没有中日、中韩等直连包**，程序会自动用英语中转：
  例如「日语 → 中文」实际走 `ja → en → zh`，只需要安装 `ja→en` 与 `en→zh` 两个包
- 语言包存放位置：`userdata\models\argos\packages\<源语言>_<目标语言>\`

**一键补齐**

「设置 → Argos 离线语言包」底部有「补齐常用语言包：日 / 韩 / 法 / 德 / 俄」按钮，
点一次会自动下载所有中转包（约 500 MB），之后这五种语言都能与中文互译。

当前开箱支持：中文 ↔ 英 / 日 / 韩 / 法 / 德 / 俄。
日、韩等非英语语言会经英语中转，准确度略低于直连模型；追求更好质量可切到 Ollama 引擎。
西班牙语等只有 BPE 格式语言包的语言，当前离线引擎不支持，请用 Ollama 翻译。

**离线机器怎么装语言包？**

方式一：把本机 `userdata\models\argos\packages` 整个目录拷过去，放到目标机同一位置即可。

方式二：在任意有网络的电脑上：
1. 打开 <https://cdn.jsdelivr.net/gh/argosopentech/argospm-index@main/index.json>
2. 搜索需要的语言对（例如 `"from_code": "ja"` 且 `"to_code": "en"`），复制其中的下载链接
3. 下载后把 `.argosmodel` 文件拷到离线电脑
4. 在「设置 → Argos 离线语言包」点「导入 .argosmodel」即可

### Ollama 本地大模型（可选）

> 官网下载地址：<https://ollama.com/download>
> 最快的方式：打开「设置 → 离线翻译环境」，点「检测并一键安装」。
> 它会先检测 Ollama 与千问模型：**本机已经装好就直接用本地的**，有 `vendor\ollama` 离线包就优先用离线包，
> 都没有才联网下载，不会重复安装。

1. 在「翻译 → 引擎」切到 Ollama
2. 安装方式二选一：
   - **有网络**：点「自动下载并安装 Ollama（约 1.6 GB）」，程序会下载官方安装包、静默安装并启动服务
   - **无网络**：把 `vendor\ollama` 目录随程序一起拷贝过去，按钮会自动变成「使用本地离线包安装 Ollama」
   - 已经装过但服务没启动时，按钮会变成「启动 Ollama 服务」
3. 模型：有离线包时点「从离线包导入模型」；有网络时在「下载模型」下拉里选一个推荐模型，
   点「下载模型」自动执行 `ollama pull`
4. 回到「使用模型」下拉选中它即可

**制作 Ollama 离线包（在有网、且已装好模型的电脑上执行一次）**

```bat
python build\make_ollama_bundle.py --models qwen3:4b --download-setup
```

会在 `vendor\ollama\` 生成：`OllamaSetup.exe`（安装包）+ `models\`（模型权重与清单）。
把这个目录和程序一起拷到离线电脑，安装后即可直接使用，全程不需要网络。

Ollama 只监听本机 `127.0.0.1:11434`，不上传数据。

---

## 五、系统声音与麦克风

系统声音使用 Windows 的 **WASAPI 回环（loopback）** 直接采集当前扬声器的播放内容，
由 `PyAudioWPatch` 完成，**不需要「立体声混音」**，也不需要安装 VB-Cable 等虚拟声卡。

- 采集参数：16-bit PCM、48 kHz、立体声，同时兼容其他采样率的输出设备
- 录制暂停时采集同步暂停，多段音频与多段视频一一对应、自动拼接
- 麦克风仍走 ffmpeg 的 DirectShow 输入，可与系统声音混音为一条立体声轨
- 如果机器没有任何音频输出设备，「录制系统声音」会自动禁用并给出提示

> 旧版本依赖「立体声混音」，而大部分 Realtek 声卡默认关闭该设备，导致"怎么设置都录不到声音"。
> 现在已改为回环采集，开箱即用。

---

## 六、目录结构

```
ScreenRecording/
├─ main.py                  程序入口（--self-test 自检，--tray 仅托盘启动）
├─ 梦星截屏.lnk              唯一的启动入口（带应用图标）
├─ build\run_console.bat    控制台模式启动（调试用）
├─ build\first_run_setup.bat 首次安装依赖
├─ build\install_offline.bat 离线安装并启动
├─ requirements.txt         运行依赖
├─ app/
│  ├─ application.py        控制器：热键 / 托盘 / 截图 / 录屏 / 翻译串联
│  ├─ config.py             配置读写（userdata/config.json）
│  ├─ paths.py              路径与 ffmpeg 查找
│  ├─ hotkeys.py            Win32 RegisterHotKey 全局热键
│  ├─ theme.py              深色主题 QSS
│  ├─ capture/              抓屏、窗口枚举
│  ├─ record/               ffmpeg 录屏、音频设备枚举
│  ├─ ocr/                  RapidOCR 封装
│  ├─ translate/            Argos 轻量引擎、Ollama、统一任务
│  └─ ui/                   遮罩、标注、录屏控制条、主窗口、托盘
├─ build/                   打包与离线依赖脚本
└─ userdata/                运行数据（配置、截图、录像、模型、日志）
```

---

## 七、常见问题

**快捷键按了没反应**
- 组合键可能被其它软件占用：到「设置」换一个，保存时会提示是否冲突
- 程序只允许开一个实例：再次双击图标会把已有窗口叫出来，不会多出一个托盘图标

**OCR 第一次识别比较慢**
- 首次调用需要加载 ONNX 模型（约 1–3 秒），之后会常驻内存

**多显示器 / 缩放比例不是 100%**
- 截图和录屏都按物理像素换算，标注坐标不会偏移
- 录屏使用主屏的缩放比例换算选区；混合缩放的多屏环境建议在分辨率一致的屏幕上录区域

**录制报「未找到 ffmpeg」**
- 程序会自动使用 `imageio-ffmpeg` 自带的 ffmpeg。若缺失，执行
  `.venv\Scripts\python.exe -m pip install imageio-ffmpeg`
- 也可以把 `ffmpeg.exe` 放到 `tools\ffmpeg\` 下

**窗口录制画面错位**
- 窗口录制基于屏幕区域捕获，录制过程中移动或最小化窗口会导致画面偏移，请保持窗口位置不变

**日志**
- 崩溃与异常堆栈写入 `userdata\logs\error.log`

---

## 八、隐私

- 截图、录像、OCR、翻译全部在本机完成
- 只有以下两种联网行为：下载 Argos 语言包索引/语言包；访问本机 Ollama 服务
- 不包含遥测、不上传任何截图或文本
