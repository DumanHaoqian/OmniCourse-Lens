# OmniCourse Lens 功能实现说明

OmniCourse Lens 现在的核心思路不是“做一个视频播放器旁边挂几个 AI 按钮”，而是把课程视频处理成一套可检索、可引用、可解释的多模态证据库。多模态，简单说就是不只看一种信息来源：系统同时使用视频画面、音频转写、课件 PDF、关键帧 OCR、公式文本、概念标签和可选的视频大模型信号。用户看到的是一个学习网站，但底层其实是一条从真实课程视频到结构化知识资产的处理链路。

## 后端整体实现

后端使用 FastAPI 实现，入口是 `backend/app/main.py`。它负责注册 API、挂载静态文件、配置 CORS，并把主要能力拆成多个 service。这里的 service 可以理解成“后端里的功能模块”：`DatasetService` 负责发现和管理真实视频，`VideoIngestService` 负责把视频转成可搜索的 evidence，`SearchService` 负责多模态检索，`EvidenceService` 负责字幕和时间戳证据，`CheatsheetService` 负责 LaTeX cheatsheet，`GraphService` 负责知识图谱，`QAAgent` 负责 AI Tutor，`LLMService` 负责 GPT-4o 调用，`DeepSeekOCRService` 和 `InternVideo3Service` 负责接入重模型。这样做的好处是每个功能边界比较清楚，后面要换 OCR 模型、换搜索策略或换前端 UI，不需要把整个系统推倒重写。

后端的数据层没有一上来引入数据库，而是用 JSON storage 做 MVP。课程文件放在 `backend/app/data/courses/`，索引放在 `backend/app/data/indexes/`，生成的 cheatsheet、graph、QA log 和 eval log 放在 `backend/app/data/generated/`，关键帧放在 `backend/app/static/frames/`。这种设计不是最终生产架构，但很适合 hackathon：可复制、可检查、可提交小型 metadata，也方便 debug。为了避免 JSON 反复读盘，`storage.py` 做了基于文件修改时间的缓存；搜索索引、字幕、视频列表和 provider status 也有缓存，所以普通搜索和播放字幕不会每次都重新扫磁盘。

后端 API 大致分三类。第一类是数据准备 API，例如 `GET /api/dataset/videos`、`POST /api/dataset/ingest`、`POST /api/index/rebuild`，它们负责发现视频、ingest 视频和重建搜索索引。第二类是用户功能 API，例如 `POST /api/search/text`、`POST /api/search/image`、`POST /api/cheatsheet`、`POST /api/knowledge-graph`、`POST /api/qa`。第三类是视频和证据 API，例如 `GET /api/dataset/videos/{video_id}/stream`、`GET /api/dataset/videos/{video_id}/subtitles`、`GET /api/dataset/videos/{video_id}/subtitles.vtt`、`GET /api/dataset/videos/{video_id}/evidence`。前端不直接读本地文件，而是通过这些 API 获取视频流、字幕、证据和模型输出。

后端的核心数据结构定义在 `backend/app/schemas.py`。里面有 `Course`、`Lecture`、`Moment`、`ASRSegment`、`OCRBlock`、`FormulaBlock`、`SearchResult`、`CheatsheetResponse`、`GraphResponse` 和 `QAResponse` 等模型。Pydantic schema 的作用是保证后端每个模块传递的数据结构稳定，比如一个 search result 必须有 `start_time`、`end_time`、`score_breakdown`、`matched_modalities` 和 evidence snippet。这样前端渲染时不用猜字段，也更容易写测试。

模型接入上，后端采用 lazy loading，也就是“用到时再加载”。DeepSeek-OCR、本地 InternVideo3、GPT-4o、faster-whisper 都可能很重，如果 API 一启动就全部加载，会慢、占 GPU，也容易因为某个模型环境不对导致整个服务挂掉。所以当前实现是：启动时只报告 provider 是否可用；真正需要 OCR、ASR、LLM 或视频 rerank 时，再进入对应 service。重模型不可用时，系统会降级到缓存、PDF 文本、启发式公式、轻量视觉描述符或 deterministic fallback，保证 demo 不会因为某个模型失败而完全不可用。

## 前端整体实现

前端使用 React + Vite + TypeScript，核心文件是 `frontend/src/App.tsx`。页面不是传统的多页面跳转，而是一个学习工作台：左边是 Dataset 视频列表和 evidence rail，中间是主视频播放器和功能输出区，右边是四个功能控制栏：Search Video、Cheatsheet、Knowledge Graph、AI Tutor。这个布局的原则是“用户主要是在看视频”，所以视频始终在中间，AI 功能围绕当前视频工作，而不是把视频挤到边角。

前端所有后端请求都集中在 `frontend/src/api.ts`。比如 `datasetVideos()` 调 `/api/dataset/videos`，`textSearch()` 调 `/api/search/text`，`imageSearch()` 调 `/api/search/image`，`askTutor()` 调 `/api/qa`，`videoSubtitles()` 调字幕 API。这样 UI 组件不需要知道具体 HTTP 细节，只关心拿到的数据怎么展示。视频播放用浏览器原生 `<video>` 标签，视频源来自 `/api/dataset/videos/{video_id}/stream`，字幕轨道来自 WebVTT，同时前端还有一个自定义字幕条，用后端返回的 cue 做更好看的动态展示。

前端的四个功能不是四个孤立页面，而是共享同一个 selected video、selected result、playback time 和 evidence 状态。Search 返回结果后，`App.tsx` 会把 `selectedResult` 设置为最相关 moment，并把主视频跳到这个 moment 的 `start_time`。QA evidence、Knowledge Graph moment node、Search result card 都可以调用同一个 `jumpToEvidence()`，所以无论用户从哪个功能点证据，都会回到中间视频播放器的对应时间点。这就是“功能围绕视频”的交互核心。

公式渲染由 `MarkdownMath`、`MathText` 和 KaTeX 完成。后端返回的答案或 evidence 里如果有 `\( ... \)` 或 `\[ ... \]`，前端会把它渲染成真正的数学公式，而不是普通字符串。Cheatsheet 页面一边显示 LaTeX source，一边用 Markdown/KaTeX 做预览；QA 页面用 Markdown + LaTeX 展示回答；搜索结果和 graph inspector 里的公式也会走同一套渲染逻辑。这样所有模型输出都尽量以可读的数学格式呈现。

Knowledge Graph 前端使用 `frontend/src/components/CytoscapeGraph.tsx`。它把后端返回的 nodes 和 edges 转成 Cytoscape elements，再用 fCoSE layout 自动排布。用户可以搜索节点、筛选节点类型、开关 label、focus 某个节点、点击节点查看 inspector。对于 moment 或 visual evidence 节点，前端会保留 timestamp、thumbnail、transcript snippet 和 formula metadata，所以用户可以从图谱直接跳回视频时间点。

前端还做了一些工程性处理。工作区左右和上下区域可以拖动调整大小，尺寸会存到 `localStorage`，下次打开还会保留。视频列表和 evidence card 使用动画，但不是为了炫，而是让状态变化更容易跟踪。Provider badge 会显示 Dataset、GPT-4o、DeepSeek OCR、InternVideo3 的可用状态，但不会把 API key 暴露到浏览器。前端只拿 provider status，真正的密钥和模型调用都留在后端。

## 真实视频数据流

系统默认读取 `/home/haoqian/Data/OmniCourse-Lens/Dataset` 里的真实课程视频，而不是只靠 mock data。后端的 `DatasetService` 会在固定 Dataset 目录下扫描 `.mp4`、`.mov`、`.mkv`、`.avi`、`.webm`、`.m4v` 等视频文件，为每个视频生成稳定的 `video_id`，并返回标题、路径、大小、时长、是否已 ingest、是否已 index、缩略图和对应 slides PDF。这里的 ingest 可以理解为“把原始视频准备成 AI 能用的数据”，index 可以理解为“把准备好的数据放进搜索库”。

当用户点击“Make Current Video Searchable”或调用 `/api/dataset/ingest` 时，系统会对视频做元数据探测、音频抽取、ASR、关键帧抽取、OCR、公式抽取和 moment 切分。moment 是视频检索里的基本单位，意思是一段带起止时间的视频片段，比如 `900-1080s`。每个 moment 都保存这段时间里的字幕、OCR 文本、公式、概念标签、关键帧和视频路径，所以后面的搜索、问答、cheatsheet 和 knowledge graph 都能引用同一套证据。

## 动态字幕

动态字幕不是前端硬猜出来的，而是后端根据真实 ASR segment 生成的。ASR 是 Automatic Speech Recognition，也就是语音转文本。系统使用 `faster-whisper` 作为主要语音识别路径，把视频音频转成带时间戳的文本片段，例如某句话从第几秒开始、第几秒结束。后端新增了 `/api/dataset/videos/{video_id}/subtitles` 和 `/api/dataset/videos/{video_id}/subtitles.vtt`，前者给前端自定义字幕条使用，后者是标准 WebVTT 字幕轨道，浏览器原生 video 也能加载。

前端播放视频时会监听当前播放时间 `currentTime`，然后在字幕 cue 里找时间范围匹配的文本。优先展示音频字幕，如果当前时间没有 ASR，就用 OCR 或 moment 文本做补充。这样用户看视频时，下面的字幕会跟着播放进度动态更新，而不是静态显示一大段 transcript。

## DeepSeek OCR 和课件文本

OCR 是 Optical Character Recognition，也就是从图片里识别文字。系统实现了 `DeepSeekOCRService`，可以发现本地 `deepseek-ai/DeepSeek-OCR` checkpoint，也支持以后接 HTTP endpoint。因为 DeepSeek-OCR 是重模型，在线搜索时如果每次上传图片都直接跑它，会非常慢，所以系统做了工程上的区分：离线 ingest 或刷新 OCR 时可以跑 DeepSeek-OCR；在线交互默认先用缓存、已有关键帧 OCR、视觉描述符和轻量 fallback，避免用户搜索时卡死。

真实课程里还有 slides PDF，所以系统也会提取 PDF 页面文本，把它作为 `slide_pdf_text` 加入 OCR evidence。这样即使某些视频帧 OCR 质量一般，搜索和问答仍然可以从课件文字里找到可靠证据。公式抽取则由 `MathOCRService` 做启发式过滤，把 OCR 文本中像公式的内容提取为 `formula_latex` 和 `formula_blocks`，并清理掉明显不是公式的噪声。

## Search Video

Search Video 的实现是 hybrid retrieval，中文可以理解成“混合检索”。它不是只查 transcript，而是给每个 moment 计算多个模态的分数：音频字幕匹配、OCR 文本匹配、公式匹配、概念标签匹配、文本向量匹配、图片视觉相似度，以及可选的 InternVideo3 视频相关性。最后系统按权重融合这些分数，返回最相关的 timestamped moments。

如果用户只搜索当前视频，但当前视频的匹配很弱，系统会做 cross-video fallback，也就是自动扩大到所有已索引视频里找更强结果，并在前端提示“当前视频没有强匹配，所以展示全库最佳结果”。这解决了“换一个视频就搜不到”的问题。用户点击搜索结果时，主播放器会自动切换到对应视频并跳到对应时间点；证据卡会展示分数、匹配模态、原因、字幕片段、OCR 片段和公式。

为了工程效率，搜索服务把索引 JSON 缓存在内存里，并用文件修改时间判断是否需要重新加载。查询 sparse vector 也只在每次搜索时构造一次，不再给每个 moment 重复构造。InternVideo3 本地 8B 模型的 subprocess rerank 默认关闭，因为冷启动太慢；如果要高质量 demo，推荐先启动持久化 InternVideo3 server，让模型只加载一次。

## InternVideo3 集成

InternVideo3 被设计成可选增强，而不是强依赖。`InternVideo3Service` 支持几种模式：如果设置了 `INTERNVIDEO3_ENDPOINT`，就走 HTTP scorer；如果有 CLI，就走命令行；如果检测到本地 checkpoint，则显示 `local_hf_lazy`，表示本地模型存在但不会在 API 启动时加载。这样不会因为一个 8B 模型拖慢整个网站启动。

在搜索里，InternVideo3 可以作为视频级 reranker，也就是用视频大模型重新判断某个 clip 和 query 是否真正相关。但为了交互速度，默认不会每次搜索都冷启动它。需要时可以设置 `INTERNVIDEO3_LOCAL_RERANK=1` 和 `INTERNVIDEO3_LOCAL_RERANK_TOP_N=1`，或者更推荐运行 `scripts/run_internvideo3_server.sh`，用 warm server 提供稳定低延迟打分。

## Cheatsheet Generation

Cheatsheet 不是凭空生成通用机器学习知识，而是从选中视频的 evidence 里组织内容。后端会读取对应 lecture 的 moments，提取核心概念、公式、算法步骤、直觉解释、常见坑点和小测题。如果 GPT-4o 可用，就让 GPT-4o 根据证据生成更自然的 LaTeX；如果不可用，就走 deterministic fallback，也就是确定性的模板生成。

生成后系统会保存 `.tex` 文件，并尝试用 `tectonic`、`pdflatex` 或 `xelatex` 编译 PDF。为了防止 LLM 生成不存在的图片路径导致编译失败，后端会清理 `\includegraphics` 这种幻觉资源，把它替换成“请在视频和关键帧面板查看视觉证据”的说明；如果出现裸 `\caption` 也会改成普通文字。前端提供 LaTeX 预览、复制、下载 `.tex`、下载 `.pdf` 和 Overleaf 导入工作流。

## Knowledge Graph

Knowledge Graph 是 educational concept graph，中文可以叫“课程概念图谱”。后端从真实 evidence 里抽取节点和边：课程、视频、moment、concept、formula 和 visual evidence 都是节点；contains、appears_in、related_to、prerequisite_of、uses_formula、shown_in_frame 这些关系是边。比如“gradient descent”会连接到讲它的 moment，也会和 “loss function”“learning rate”“negative gradient” 产生关系。

前端使用 Cytoscape.js 和 fCoSE layout。Cytoscape.js 是一个专业图可视化库，fCoSE 是 force-directed layout，也就是用类似物理力的布局算法把节点拉开，减少重叠。系统还做了 graph pruning，也就是图谱剪枝：默认限制概念和边的数量，保留高频、公式、先修关系和关键证据，避免图谱密得看不懂。用户可以搜索节点、过滤节点类型、点击节点查看证据，并从 moment 节点跳回视频时间点。

## AI Tutor

AI Tutor 是 retrieval-first QA，也就是“先检索，再回答”。当用户提问时，系统先调用 Search Video 找相关 moment，如果用户上传图片，会结合图片 OCR 和视觉检索；如果用户正在看某个时间点，还会加入附近 moment 作为上下文。然后后端把字幕、OCR、公式、时间戳、缩略图和匹配原因组成 evidence pack，再交给 GPT-4o 或 fallback 生成答案。

答案要求使用 Markdown + LaTeX。Markdown 负责段落、列表和加粗，LaTeX 负责公式，比如梯度下降更新式会以 `\[ \theta^{[t+1]} = \theta^{[t]} - \alpha \nabla_\theta J(\theta^{[t]}) \]` 这种形式返回，前端用 KaTeX 渲染成真正的数学公式。回答后还会返回 evidence cards，用户能看到答案来自哪个 lecture、哪个 timestamp、哪段字幕、哪段 OCR 和哪个公式。

## 自检和工程效率

系统有 runtime self-check，也就是每次搜索、QA、cheatsheet 和 graph 生成后会做一个轻量评估，检查是否有证据、是否有时间戳、是否有公式、是否多模态、结果是否太弱。如果分数低，部分功能会自动扩大检索或补充证据。开发侧也有 `scripts/smoke_test.py`，它会测试真实 Dataset 视频发现、ingest、搜索、字幕、图像搜索、QA、cheatsheet 编译、graph 和 provider status。

最近还加入了性能自检 `scripts/perf_check.py`，用于测用户最常走的热路径：health、Dataset 视频列表、字幕接口和当前视频搜索。工程上做了多层缓存：课程 JSON 缓存、Dataset 列表 TTL 缓存、证据索引缓存、subtitle/VTT 缓存、provider status 缓存和搜索索引缓存。这样页面刷新、切视频、播放字幕和普通搜索不会重复扫磁盘或重复探测大模型。

## 总结

这套 MVP 的核心价值是把真实课程视频变成可搜索、可解释、可生成学习材料的多模态知识库。视频仍然是产品中心，AI 功能只是围绕视频工作：搜索帮用户找到时间点，字幕帮用户跟着看，QA 帮用户解释当前问题，cheatsheet 帮用户复习，knowledge graph 帮用户理解概念关系。重模型如 DeepSeek-OCR、InternVideo3、GPT-4o 都被接入为增强能力，但系统不会因为它们不可用或冷启动慢而整体失效，这也是当前实现里最重要的工程取舍。
